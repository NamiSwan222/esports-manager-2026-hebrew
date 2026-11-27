//! Right-to-left Hebrew in TextMeshPro (IL2CPP games), enabled by `rtl=tmp` in redirect.cfg.
//!
//! TextMeshPro has no bidi: a logical Hebrew string is drawn left to right, i.e. mirrored. We hook the
//! two ways text gets into a TextMeshPro component, `TMP_Text.text` (setter) and `TMP_Text.SetText(string)`.
//! When the new text has Hebrew letters, the component gets `isRightToLeftText = true` (TextMeshPro then
//! lays the characters out from the right edge and still wraps lines in string order, so line order is
//! right) and the string is passed through `rtl::tmp_rtl` (Latin/number runs reversed, brackets mirrored).
//! Text without Hebrew turns `isRightToLeftText` back off on components we switched. With `rtl=tmp-right`
//! left-aligned Hebrew texts are also right-aligned (and put back for non-Hebrew text).
//!
//! Hooks are installed right after `il2cpp_init` (we hand UnityPlayer a wrapper from GetProcAddress),
//! before any managed code runs. The game's code is not modified in place: a hooked method's pointer is
//! replaced in its MethodInfo (reflection, UnityEvent/delegates, vtables built later), in already built
//! vtables, in GameAssembly's method pointer table, and at direct `call`/`jmp rel32` sites (through a jump
//! stub allocated near GameAssembly).
use crate::{dates, rtl, sha};
use crate::{log, GetModuleHandleW, GetProcAddress, Handle, VirtualProtect};
use core::ffi::c_void;
use std::collections::{HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::sync::Mutex;

#[repr(C)]
struct MemInfo {
    base: usize,
    alloc_base: usize,
    alloc_protect: u32,
    partition: u16,
    region_size: usize,
    state: u32,
    protect: u32,
    kind: u32,
}

#[link(name = "kernel32")]
extern "system" {
    fn VirtualAlloc(addr: *mut c_void, size: usize, kind: u32, protect: u32) -> *mut c_void;
    fn VirtualQuery(addr: *const c_void, info: *mut MemInfo, len: usize) -> usize;
}

type P = *mut c_void;

#[allow(clippy::type_complexity)]
struct Api {
    domain_get: unsafe extern "C" fn() -> P,
    domain_get_assemblies: unsafe extern "C" fn(P, *mut usize) -> *const P,
    assembly_get_image: unsafe extern "C" fn(P) -> P,
    image_get_class_count: unsafe extern "C" fn(P) -> usize,
    image_get_class: unsafe extern "C" fn(P, usize) -> P,
    class_from_name: unsafe extern "C" fn(P, *const u8, *const u8) -> P,
    class_get_methods: unsafe extern "C" fn(P, *mut P) -> P,
    class_is_subclass_of: unsafe extern "C" fn(P, P, bool) -> bool,
    method_get_name: unsafe extern "C" fn(P) -> *const u8,
    method_get_param_count: unsafe extern "C" fn(P) -> u32,
    method_get_param: unsafe extern "C" fn(P, u32) -> P,
    type_get_type: unsafe extern "C" fn(P) -> i32,
    object_get_class: unsafe extern "C" fn(P) -> P,
    string_length: unsafe extern "C" fn(P) -> i32,
    string_chars: unsafe extern "C" fn(P) -> *const u16,
    string_new_utf16: unsafe extern "C" fn(*const u16, i32) -> P,
}

const T_BOOL: i32 = 0x02;
const T_STRING: i32 = 0x0e;

static mut API: Option<Api> = None;
static mut ALIGN: bool = false;
static mut TMP_TEXT: usize = 0;
static mut ORIG: [usize; 3] = [0; 3]; // set_text, SetText(string), SetText(string, bool)
static mut SET_RTL: (usize, usize) = (0, 0); // set_isRightToLeftText: code, MethodInfo
static mut GET_HALIGN: (usize, usize) = (0, 0);
static mut SET_HALIGN: (usize, usize) = (0, 0);
pub static mut ORIG_INIT: usize = 0;
pub static mut ORIG_INIT16: usize = 0;
pub static mut GAME_ASSEMBLY: Handle = core::ptr::null_mut();

struct Seen {
    tmp_classes: HashSet<usize>,
    other_classes: HashSet<usize>,
    flipped: HashMap<usize, bool>, // component -> we right-aligned it
    done: HashSet<u64>,            // hashes of strings we produced (or that need no change)
}
static SEEN: Mutex<Option<Seen>> = Mutex::new(None);

// The pack's lookup files carry no English: every English text is known by `sha::key` (16 hex digits of
// SHA-256 over its UTF-8 bytes, tools/common.py `H`). The hooks hash the text TextMeshPro is given (or a part
// of it, below) and look the key up. Values are Hebrew, escaped (`\n`, `\t`, `\\`).

/// `labels=<file>` in redirect.cfg: lines `KEY<TAB>Hebrew` (the exact English text) and `^KEY<TAB>Hebrew`
/// (the key of the upper-cased English, for texts the game upper-cases before showing; build.py writes them).
static mut LABELS: Option<Labels> = None;
/// `bios=<file>`: player bios, swapped only as the whole text (a career keeps the bio it copied from the
/// database, and the profile sets it whole). Lines `KEY<TAB>Hebrew`, and templates `*<TAB>KEY<TAB>Hebrew with
/// {0}, {1}..`: KEY of the text's skeleton (see `skeleton`; the FaceIt bio, whose numbers differ per career).
static mut BIOS: Option<Bios> = None;
/// `keep=<file>`: keys of texts that stay in Latin on purpose (names, brands), one per line; not logged.
static mut KEEP: Option<Keep> = None;
/// Text log (`-tirgumim_textlog`, or a file `textlog.on` in the data folder): every distinct text without
/// Hebrew that is set on a TextMeshPro component and is neither a label nor in the keep list goes to
/// `<data folder>\textlog.txt` (one per line, escaped like the labels file), to find untranslated text.
/// The log is the player's own local file; it is never part of the pack.
static mut TEXTLOG: Option<std::path::PathBuf> = None;
static LOGGED: Mutex<Option<HashSet<u64>>> = Mutex::new(None);

fn unescape(s: &str) -> String {
    let mut o = String::new();
    let mut it = s.chars();
    while let Some(c) = it.next() {
        if c == '\\' {
            match it.next() {
                Some('n') => o.push('\n'),
                Some('r') => o.push('\r'),
                Some('t') => o.push('\t'),
                Some(x) => o.push(x),
                None => o.push('\\'),
            }
        } else {
            o.push(c);
        }
    }
    o
}

pub fn escape(s: &str) -> String {
    s.replace('\\', "\\\\").replace('\n', "\\n").replace('\r', "\\r").replace('\t', "\\t")
}

fn w16(s: &str) -> Vec<u16> {
    unescape(s).encode_utf16().collect()
}

fn is_space(c: u16) -> bool {
    matches!(c, 0x20 | 0x09 | 0x0a | 0x0d | 0xa0 | 0x200b)
}

#[derive(Default)]
pub struct Labels {
    exact: HashMap<u64, Vec<u16>>,
    up: HashMap<u64, Vec<u16>>,
}

impl Labels {
    pub fn parse(txt: &str) -> Labels {
        let mut l = Labels::default();
        for line in txt.lines() {
            let Some((k, he)) = line.split_once('\t') else { continue };
            if he.is_empty() {
                continue;
            }
            let (map, k) = match k.strip_prefix('^') {
                Some(k) => (&mut l.up, k),
                None => (&mut l.exact, k),
            };
            if let Some(k) = sha::parse_key(k) {
                map.entry(k).or_insert_with(|| w16(he));
            }
        }
        l
    }

    /// A label for exactly `t`, also when the game upper-cased it.
    fn lookup(&self, t: &[u16]) -> Option<&Vec<u16>> {
        let k = sha::key(t);
        if let Some(v) = self.exact.get(&k) {
            return Some(v);
        }
        let has_lower = t.iter().any(|&c| (b'a' as u16..=b'z' as u16).contains(&c));
        let has_upper = t.iter().any(|&c| (b'A' as u16..=b'Z' as u16).contains(&c));
        if has_upper && !has_lower {
            return self.up.get(&k);
        }
        None
    }

    pub fn label_for(&self, t: &[u16]) -> Option<Vec<u16>> {
        label_for_with(t, &|s| self.lookup(s).cloned())
    }
}

/// `t` with a label for its core (without surrounding spaces and a trailing colon).
fn label_run(t: &[u16], look: &dyn Fn(&[u16]) -> Option<Vec<u16>>) -> Option<Vec<u16>> {
    let mut a = 0;
    let mut b = t.len();
    while a < b && is_space(t[a]) {
        a += 1;
    }
    while b > a && (is_space(t[b - 1]) || t[b - 1] == b':' as u16) {
        b -= 1;
    }
    if a == b {
        return None;
    }
    let he = look(&t[a..b])?;
    Some([&t[..a], he.as_slice(), &t[b..]].concat())
}

/// The Hebrew display text for an English text: a whole label, or labels for the runs between rich-text
/// tags and line breaks ("<b>Rating</b>\n15" -> "<b>דירוג</b>\n15"). `look` finds the label of one candidate
/// (the whole text, a trimmed run).
fn label_for_with(t: &[u16], look: &dyn Fn(&[u16]) -> Option<Vec<u16>>) -> Option<Vec<u16>> {
    if let Some(v) = look(t) {
        return Some(v);
    }
    if let Some(v) = label_run(t, look) {
        return Some(v);
    }
    if !t.iter().any(|&c| c == b'<' as u16 || c == b'\n' as u16) {
        return None;
    }
    let mut out = Vec::with_capacity(t.len() + 16);
    let mut changed = false;
    let mut i = 0;
    while i < t.len() {
        if t[i] == b'<' as u16 {
            let end = t[i..].iter().position(|&c| c == b'>' as u16).map(|p| i + p + 1).unwrap_or(t.len());
            out.extend_from_slice(&t[i..end]);
            i = end;
            continue;
        }
        let end = t[i..].iter().position(|&c| c == b'<' as u16 || c == b'\n' as u16).map(|p| i + p).unwrap_or(t.len());
        let run = &t[i..end];
        match label_run(run, look) {
            Some(v) => {
                out.extend_from_slice(&v);
                changed = true;
            }
            None => out.extend_from_slice(run),
        }
        if end < t.len() && t[end] == b'\n' as u16 {
            out.push(b'\n' as u16);
            i = end + 1;
        } else {
            i = end;
        }
    }
    if changed { Some(out) } else { None }
}

fn is_digit(c: u16) -> bool {
    (b'0' as u16..=b'9' as u16).contains(&c)
}

fn is_cap(c: u16) -> bool {
    (b'A' as u16..=b'Z' as u16).contains(&c)
}

fn is_alnum(c: u16) -> bool {
    is_digit(c) || is_cap(c) || (b'a' as u16..=b'z' as u16).contains(&c)
}

/// The bio-template normalisation (tools/sources.py `skeleton`, the same rules): `t` with each hole replaced
/// by `{}`, and the holes. A hole starts at the start or after a character that is not an ASCII letter or digit,
/// and is either a number-like token (an ASCII digit, then ASCII letters and digits, a `.` between two of them,
/// a space before another digit: "17.02.2019", "1.47", "2 308", "248u") or a word of 2-4 ASCII capitals ("EU").
pub fn skeleton(t: &[u16]) -> (Vec<u16>, Vec<&[u16]>) {
    let n = t.len();
    let mut out = Vec::with_capacity(n);
    let mut holes = Vec::new();
    let mut i = 0;
    while i < n {
        let c = t[i];
        let start = i == 0 || !is_alnum(t[i - 1]);
        if start && is_digit(c) {
            let mut j = i;
            loop {
                while j < n && is_alnum(t[j]) {
                    j += 1;
                }
                if j + 1 < n && t[j] == b'.' as u16 && is_alnum(t[j + 1]) {
                    j += 1;
                } else if j + 1 < n && t[j] == b' ' as u16 && is_digit(t[j + 1]) {
                    j += 1;
                } else {
                    break;
                }
            }
            holes.push(&t[i..j]);
            out.extend_from_slice(&[b'{' as u16, b'}' as u16]);
            i = j;
            continue;
        }
        if start && is_cap(c) {
            let mut j = i;
            while j < n && is_cap(t[j]) {
                j += 1;
            }
            if (2..=4).contains(&(j - i)) && !(j < n && is_alnum(t[j])) {
                holes.push(&t[i..j]);
                out.extend_from_slice(&[b'{' as u16, b'}' as u16]);
                i = j;
                continue;
            }
        }
        out.push(c);
        i += 1;
    }
    (out, holes)
}

/// `he` with `{N}` replaced by hole N.
fn fill(he: &[u16], holes: &[&[u16]]) -> Vec<u16> {
    let mut out = Vec::with_capacity(he.len() + 64);
    let mut i = 0;
    while i < he.len() {
        if he[i] == b'{' as u16 {
            let d = he[i + 1..].iter().take_while(|&&c| is_digit(c)).count();
            if d > 0 && he.get(i + 1 + d) == Some(&(b'}' as u16)) {
                let k = String::from_utf16_lossy(&he[i + 1..i + 1 + d]).parse::<usize>().unwrap_or(usize::MAX);
                if let Some(h) = holes.get(k) {
                    out.extend_from_slice(h);
                    i += d + 2;
                    continue;
                }
            }
        }
        out.push(he[i]);
        i += 1;
    }
    out
}

#[derive(Default)]
pub struct Bios {
    exact: HashMap<u64, Vec<u16>>,
    templates: HashMap<u64, Vec<u16>>,
}

impl Bios {
    pub fn parse(txt: &str) -> Bios {
        let mut b = Bios::default();
        for line in txt.lines() {
            let f: Vec<&str> = line.split('\t').collect();
            match f.as_slice() {
                ["*", k, he] if !he.is_empty() => {
                    if let Some(k) = sha::parse_key(k) {
                        b.templates.insert(k, w16(he));
                    }
                }
                [k, he] if !he.is_empty() => {
                    if let Some(k) = sha::parse_key(k) {
                        b.exact.insert(k, w16(he));
                    }
                }
                _ => {}
            }
        }
        b
    }

    pub fn counts(&self) -> (usize, usize) {
        (self.exact.len(), self.templates.len())
    }

    /// The Hebrew bio for exactly `t` (for a template: surrounding spaces kept), or None.
    pub fn bio_for(&self, t: &[u16]) -> Option<Vec<u16>> {
        if let Some(v) = self.exact.get(&sha::key(t)) {
            return Some(v.clone());
        }
        if self.templates.is_empty() {
            return None;
        }
        let a = t.iter().position(|&c| !is_space(c))?;
        let b = t.len() - t.iter().rev().position(|&c| !is_space(c))?;
        let core = &t[a..b];
        if !core.iter().any(|&c| is_digit(c) || is_cap(c)) {
            return None;
        }
        let (sk, holes) = skeleton(core);
        if holes.is_empty() {
            return None;
        }
        let he = self.templates.get(&sha::key(&sk))?;
        Some([&t[..a], fill(he, &holes).as_slice(), &t[b..]].concat())
    }
}

#[derive(Default)]
pub struct Keep(HashSet<u64>);

impl Keep {
    pub fn parse(txt: &str) -> Keep {
        Keep(txt.lines().filter_map(|l| sha::parse_key(l.trim_end())).collect())
    }

    /// `t` (or `t` without surrounding white space) is a kept text.
    pub fn has(&self, t: &[u16]) -> bool {
        let s = String::from_utf16_lossy(t);
        self.0.contains(&sha::key_str(&s)) || self.0.contains(&sha::key_str(s.trim()))
    }
}

pub unsafe fn load_labels(path: &str) -> usize {
    let Ok(txt) = std::fs::read_to_string(path) else { return 0 };
    let l = Labels::parse(&txt);
    let n = l.exact.len();
    LABELS = Some(l);
    n
}

/// Returns (exact bios, templates).
pub unsafe fn load_bios(path: &str) -> (usize, usize) {
    let Ok(txt) = std::fs::read_to_string(path) else { return (0, 0) };
    let b = Bios::parse(&txt);
    let n = b.counts();
    BIOS = Some(b);
    n
}

pub unsafe fn load_keep(path: &str) -> usize {
    let Ok(txt) = std::fs::read_to_string(path) else { return 0 };
    let k = Keep::parse(&txt);
    let n = k.0.len();
    KEEP = Some(k);
    n
}

pub unsafe fn enable_textlog(path: std::path::PathBuf) {
    TEXTLOG = Some(path);
}

unsafe fn bio_for(t: &[u16]) -> Option<Vec<u16>> {
    BIOS.as_ref()?.bio_for(t)
}

unsafe fn label_for(t: &[u16]) -> Option<Vec<u16>> {
    LABELS.as_ref()?.label_for(t)
}

/// The line the text log writes for `text`, or None (fewer than two Latin letters, or a kept text).
fn log_line(keep: Option<&Keep>, text: &[u16]) -> Option<String> {
    let s = String::from_utf16_lossy(text);
    if s.chars().filter(|c| c.is_ascii_alphabetic()).count() < 2 {
        return None;
    }
    if keep.is_some_and(|k| k.has(text)) {
        return None;
    }
    Some(escape(&s))
}

fn text_log(text: &[u16]) {
    let Some(path) = (unsafe { TEXTLOG.as_ref() }) else { return };
    let Some(line) = log_line(unsafe { KEEP.as_ref() }, text) else { return };
    let h = hash(text);
    let mut g = LOGGED.lock().unwrap();
    if !g.get_or_insert_with(HashSet::new).insert(h) {
        return;
    }
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{line}");
    }
}

const H_LEFT: i32 = 1;
const H_RIGHT: i32 = 4;

fn hash(s: &[u16]) -> u64 {
    let mut h = std::collections::hash_map::DefaultHasher::new();
    s.hash(&mut h);
    h.finish()
}

unsafe fn is_tmp(a: &Api, obj: P) -> bool {
    let k = (a.object_get_class)(obj) as usize;
    if k == 0 {
        return false;
    }
    {
        let g = SEEN.lock().unwrap();
        let s = g.as_ref().unwrap();
        if s.tmp_classes.contains(&k) {
            return true;
        }
        if s.other_classes.contains(&k) {
            return false;
        }
    }
    let yes = k == TMP_TEXT || (a.class_is_subclass_of)(k as P, TMP_TEXT as P, false);
    let mut g = SEEN.lock().unwrap();
    let s = g.as_mut().unwrap();
    if yes { s.tmp_classes.insert(k) } else { s.other_classes.insert(k) };
    yes
}

unsafe fn set_rtl(obj: P, on: bool) {
    if SET_RTL.0 != 0 {
        let f: unsafe extern "C" fn(P, bool, usize) = core::mem::transmute(SET_RTL.0);
        f(obj, on, SET_RTL.1);
    }
}

unsafe fn halign(obj: P) -> i32 {
    let f: unsafe extern "C" fn(P, usize) -> i32 = core::mem::transmute(GET_HALIGN.0);
    f(obj, GET_HALIGN.1)
}

unsafe fn set_halign(obj: P, v: i32) {
    let f: unsafe extern "C" fn(P, i32, usize) = core::mem::transmute(SET_HALIGN.0);
    f(obj, v, SET_HALIGN.1);
}

/// The string to hand to TextMeshPro instead of `s` (and the component switched to right-to-left).
unsafe fn process(obj: P, s: P) -> P {
    let Some(a) = API.as_ref() else { return s };
    if obj.is_null() || TMP_TEXT == 0 || !is_tmp(a, obj) {
        return s;
    }
    let text: &[u16] = if s.is_null() {
        &[]
    } else {
        let n = (a.string_length)(s).max(0) as usize;
        let p = (a.string_chars)(s);
        if p.is_null() { &[] } else { core::slice::from_raw_parts(p, n) }
    };
    let can_align = ALIGN && GET_HALIGN.0 != 0 && SET_HALIGN.0 != 0;
    let mut s = s;
    let mut text = text;
    // Hebrew for display only (code keys stay English), in this order: a player bio as stored in the career
    // save (whole text), English dates built at run time (date shapes anywhere in the text, also inside
    // Hebrew text), English UI labels (whole text or the runs between tags)
    let bio = if rtl::has_rtl(text) { None } else { bio_for(text) };
    let dated = if bio.is_some() { None } else { dates::apply(text) };
    let label = if bio.is_some() || dated.as_ref().is_some_and(|d| rtl::has_rtl(d)) || rtl::has_rtl(text) {
        None
    } else {
        label_for(dated.as_deref().unwrap_or(text))
    };
    if let Some(he) = label.as_ref().or(dated.as_ref()).or(bio.as_ref()) {
        let ns = (a.string_new_utf16)(he.as_ptr(), he.len() as i32);
        if !ns.is_null() {
            s = ns;
            text = he.as_slice();
        }
    }
    if !rtl::has_rtl(text) {
        text_log(text);
    }
    if !rtl::has_rtl(text) {
        let was = SEEN.lock().unwrap().as_mut().unwrap().flipped.remove(&(obj as usize));
        if let Some(aligned) = was {
            set_rtl(obj, false);
            if aligned && can_align && halign(obj) == H_RIGHT {
                set_halign(obj, H_LEFT);
            }
        }
        return s;
    }
    let known = SEEN.lock().unwrap().as_ref().unwrap().flipped.contains_key(&(obj as usize));
    set_rtl(obj, true);
    if !known {
        let aligned = can_align && halign(obj) == H_LEFT;
        if aligned {
            set_halign(obj, H_RIGHT);
        }
        SEEN.lock().unwrap().as_mut().unwrap().flipped.insert(obj as usize, aligned);
    }
    let h = hash(text);
    if SEEN.lock().unwrap().as_ref().unwrap().done.contains(&h) {
        return s; // already in TextMeshPro order (e.g. the game read .text back and set it again)
    }
    let out = rtl::tmp_rtl(text);
    let mut g = SEEN.lock().unwrap();
    let st = g.as_mut().unwrap();
    if st.done.len() > 200_000 {
        st.done.clear();
    }
    if out == text {
        st.done.insert(h);
        return s;
    }
    st.done.insert(hash(&out));
    drop(g);
    let ns = (a.string_new_utf16)(out.as_ptr(), out.len() as i32);
    if ns.is_null() { s } else { ns }
}

// TextMeshPro methods have at most these four register arguments (this, string, [bool,] MethodInfo*);
// passing four along is fine for the shorter ones.
type Fn4 = unsafe extern "C" fn(P, P, P, P);
unsafe extern "C" fn h_set_text(o: P, s: P, a: P, b: P) {
    let s = process(o, s);
    core::mem::transmute::<usize, Fn4>(ORIG[0])(o, s, a, b)
}
unsafe extern "C" fn h_settext1(o: P, s: P, a: P, b: P) {
    let s = process(o, s);
    core::mem::transmute::<usize, Fn4>(ORIG[1])(o, s, a, b)
}
unsafe extern "C" fn h_settext2(o: P, s: P, a: P, b: P) {
    let s = process(o, s);
    core::mem::transmute::<usize, Fn4>(ORIG[2])(o, s, a, b)
}

pub unsafe extern "C" fn h_il2cpp_init(domain: *const u8) -> i32 {
    let f: unsafe extern "C" fn(*const u8) -> i32 = core::mem::transmute(ORIG_INIT);
    let r = f(domain);
    log(&format!("il2cpp_init -> {r}; {}", install(GAME_ASSEMBLY)));
    r
}
pub unsafe extern "C" fn h_il2cpp_init_utf16(domain: *const u16) -> i32 {
    let f: unsafe extern "C" fn(*const u16) -> i32 = core::mem::transmute(ORIG_INIT16);
    let r = f(domain);
    log(&format!("il2cpp_init_utf16 -> {r}; {}", install(GAME_ASSEMBLY)));
    r
}

/// GetProcAddress as UnityPlayer sees it: il2cpp_init(_utf16) come back as our wrappers.
pub unsafe extern "system" fn h_getprocaddress(m: Handle, name: *const u8) -> *mut c_void {
    let r = GetProcAddress(m, name);
    if r.is_null() || (name as usize) < 0x10000 {
        return r;
    }
    let n = core::ffi::CStr::from_ptr(name as *const i8).to_bytes();
    if n == b"il2cpp_init" {
        ORIG_INIT = r as usize;
        GAME_ASSEMBLY = m;
        return h_il2cpp_init as *const () as *mut c_void;
    }
    if n == b"il2cpp_init_utf16" {
        ORIG_INIT16 = r as usize;
        GAME_ASSEMBLY = m;
        return h_il2cpp_init_utf16 as *const () as *mut c_void;
    }
    r
}

pub unsafe fn enable(align: bool) {
    ALIGN = align;
}

unsafe fn api(ga: Handle) -> Option<Api> {
    macro_rules! f {
        ($n:literal) => {{
            let p = GetProcAddress(ga, concat!($n, "\0").as_ptr());
            if p.is_null() {
                log(concat!("rtl: missing ", $n));
                return None;
            }
            core::mem::transmute::<*mut c_void, _>(p)
        }};
    }
    Some(Api {
        domain_get: f!("il2cpp_domain_get"),
        domain_get_assemblies: f!("il2cpp_domain_get_assemblies"),
        assembly_get_image: f!("il2cpp_assembly_get_image"),
        image_get_class_count: f!("il2cpp_image_get_class_count"),
        image_get_class: f!("il2cpp_image_get_class"),
        class_from_name: f!("il2cpp_class_from_name"),
        class_get_methods: f!("il2cpp_class_get_methods"),
        class_is_subclass_of: f!("il2cpp_class_is_subclass_of"),
        method_get_name: f!("il2cpp_method_get_name"),
        method_get_param_count: f!("il2cpp_method_get_param_count"),
        method_get_param: f!("il2cpp_method_get_param"),
        type_get_type: f!("il2cpp_type_get_type"),
        object_get_class: f!("il2cpp_object_get_class"),
        string_length: f!("il2cpp_string_length"),
        string_chars: f!("il2cpp_string_chars"),
        string_new_utf16: f!("il2cpp_string_new_utf16"),
    })
}

unsafe fn methods(a: &Api, k: P) -> Vec<P> {
    let mut it: P = core::ptr::null_mut();
    let mut v = vec![];
    loop {
        let m = (a.class_get_methods)(k, &mut it);
        if m.is_null() {
            return v;
        }
        v.push(m);
    }
}

unsafe fn sig(a: &Api, m: P) -> (&'static [u8], Vec<i32>) {
    let n = core::ffi::CStr::from_ptr((a.method_get_name)(m) as *const i8).to_bytes();
    let pars = (0..(a.method_get_param_count)(m)).map(|i| (a.type_get_type)((a.method_get_param)(m, i))).collect();
    (n, pars)
}

unsafe fn writable(addr: usize) -> bool {
    let mut mi: MemInfo = core::mem::zeroed();
    VirtualQuery(addr as *const c_void, &mut mi, core::mem::size_of::<MemInfo>()) != 0
        && mi.state == 0x1000
        && matches!(mi.protect & 0xff, 0x04 | 0x08 | 0x40 | 0x80)
}

/// Readable committed bytes from `addr`, at most `max`.
unsafe fn readable_len(addr: usize, max: usize) -> usize {
    let mut n = 0;
    while n < max {
        let mut mi: MemInfo = core::mem::zeroed();
        if VirtualQuery((addr + n) as *const c_void, &mut mi, core::mem::size_of::<MemInfo>()) == 0
            || mi.state != 0x1000
            || mi.protect & 0x101 != 0
            || mi.protect == 0
        {
            break;
        }
        n = (mi.base + mi.region_size) - addr;
    }
    n.min(max)
}

unsafe fn write_bytes(addr: usize, bytes: &[u8]) -> bool {
    let mut old = 0u32;
    if VirtualProtect(addr as *mut c_void, bytes.len(), 0x40, &mut old) == 0 {
        return false;
    }
    core::ptr::copy_nonoverlapping(bytes.as_ptr(), addr as *mut u8, bytes.len());
    VirtualProtect(addr as *mut c_void, bytes.len(), old, &mut old);
    true
}

/// (rva, size, characteristics) of each section.
unsafe fn sections(base: usize) -> Vec<(usize, usize, u32)> {
    let rd32 = |o: usize| core::ptr::read_unaligned((base + o) as *const u32);
    let rd16 = |o: usize| core::ptr::read_unaligned((base + o) as *const u16);
    let nt = rd32(0x3c) as usize;
    let n = rd16(nt + 6) as usize;
    let first = nt + 24 + rd16(nt + 20) as usize;
    (0..n).map(|i| (rd32(first + i * 40 + 12) as usize, rd32(first + i * 40 + 8) as usize, rd32(first + i * 40 + 36))).collect()
}

/// A page for jump stubs within ±2 GB of the module (for rel32 calls).
unsafe fn alloc_near(base: usize, size: usize) -> usize {
    let g = 0x10000;
    let mut a = (base & !(g - 1)).saturating_sub(g);
    let lo = base.saturating_sub(0x7000_0000);
    while a > lo {
        let p = VirtualAlloc(a as P, 0x1000, 0x3000, 0x40);
        if !p.is_null() {
            return p as usize;
        }
        a -= g;
    }
    let mut a = (base + size + g) & !(g - 1);
    while a < base + 0x7000_0000 {
        let p = VirtualAlloc(a as P, 0x1000, 0x3000, 0x40);
        if !p.is_null() {
            return p as usize;
        }
        a += g;
    }
    0
}

/// Point every use of `orig` at `hook`. Returns (MethodInfos, vtable slots, pointer table entries, call sites).
unsafe fn redirect(base: usize, orig: usize, hook: usize, infos: &[P], classes: &[P], stub: usize) -> [usize; 4] {
    let mut c = [0usize; 4];
    let mut mis = vec![];
    for &m in infos {
        let w = m as *mut usize;
        let mut hit = false;
        for i in 0..2 {
            if *w.add(i) == orig && writable(w.add(i) as usize) {
                *w.add(i) = hook;
                hit = true;
            }
        }
        if hit {
            c[0] += 1;
            mis.push(m as usize);
        }
    }
    for &k in classes {
        let n = readable_len(k as usize, 0x10000) / 8;
        let w = k as *mut usize;
        for i in 0..n.saturating_sub(1) {
            if *w.add(i) == orig && mis.contains(&*w.add(i + 1)) && writable(w.add(i) as usize) {
                *w.add(i) = hook;
                c[1] += 1;
            }
        }
    }
    if stub != 0 {
        let mut s = [0xFFu8, 0x25, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        s[6..].copy_from_slice(&hook.to_le_bytes());
        core::ptr::copy_nonoverlapping(s.as_ptr(), stub as *mut u8, s.len());
    }
    for (rva, size, ch) in sections(base) {
        let start = base + rva;
        if ch & 0x2000_0000 != 0 {
            if stub == 0 {
                continue;
            }
            let b = core::slice::from_raw_parts(start as *const u8, size);
            let mut i = 0;
            while i + 5 <= size {
                if b[i] == 0xE8 || b[i] == 0xE9 {
                    let rel = i32::from_le_bytes([b[i + 1], b[i + 2], b[i + 3], b[i + 4]]) as isize;
                    let site = start + i;
                    if (site as isize + 5 + rel) as usize == orig {
                        let nrel = stub as isize - (site as isize + 5);
                        if nrel >= i32::MIN as isize && nrel <= i32::MAX as isize && write_bytes(site + 1, &(nrel as i32).to_le_bytes()) {
                            c[3] += 1;
                        }
                        i += 5;
                        continue;
                    }
                }
                i += 1;
            }
        } else if ch & 0x8000_0000 != 0 {
            let w = start as *const usize;
            for i in 0..size / 8 {
                if core::ptr::read(w.add(i)) == orig && write_bytes(start + i * 8, &hook.to_le_bytes()) {
                    c[2] += 1;
                }
            }
        }
    }
    c
}

/// Find TextMeshPro and hook it. Returns a line for the log.
pub unsafe fn install(ga: Handle) -> String {
    if ga.is_null() || TMP_TEXT != 0 {
        return "rtl: no GameAssembly or already installed".into();
    }
    let Some(a) = api(ga) else { return "rtl: il2cpp API incomplete".into() };
    *SEEN.lock().unwrap() = Some(Seen { tmp_classes: HashSet::new(), other_classes: HashSet::new(), flipped: HashMap::new(), done: HashSet::new() });
    let mut n = 0usize;
    let asms = (a.domain_get_assemblies)((a.domain_get)(), &mut n);
    if asms.is_null() {
        return "rtl: no assemblies".into();
    }
    let images: Vec<P> = (0..n).map(|i| (a.assembly_get_image)(*asms.add(i))).collect();
    let tmp = images.iter().map(|&im| (a.class_from_name)(im, b"TMPro\0".as_ptr(), b"TMP_Text\0".as_ptr())).find(|k| !k.is_null());
    let Some(tmp) = tmp else { return "rtl: TMPro.TMP_Text not found".into() };
    let mut classes = vec![tmp];
    for &im in &images {
        for i in 0..(a.image_get_class_count)(im) {
            let k = (a.image_get_class)(im, i);
            if !k.is_null() && k != tmp && (a.class_is_subclass_of)(k, tmp, false) {
                classes.push(k);
            }
        }
    }
    let mut infos = vec![];
    let mut targets = [0usize; 3];
    for &k in &classes {
        for m in methods(&a, k) {
            infos.push(m);
            if k != tmp {
                continue;
            }
            let code = *(m as *const usize);
            match sig(&a, m) {
                (b"set_text", p) if p == [T_STRING] => targets[0] = code,
                (b"SetText", p) if p == [T_STRING] => targets[1] = code,
                (b"SetText", p) if p == [T_STRING, T_BOOL] => targets[2] = code,
                (b"set_isRightToLeftText", p) if p == [T_BOOL] => SET_RTL = (code, m as usize),
                (b"get_horizontalAlignment", p) if p.is_empty() => GET_HALIGN = (code, m as usize),
                (b"set_horizontalAlignment", p) if p.len() == 1 => SET_HALIGN = (code, m as usize),
                _ => {}
            }
        }
    }
    if targets[0] == 0 || SET_RTL.0 == 0 {
        return format!("rtl: set_text {:#x} / set_isRightToLeftText {:#x} not found", targets[0], SET_RTL.0);
    }
    if targets[2] == targets[1] {
        targets[2] = 0; // SetText(string) and SetText(string, bool) share one body
    }
    let base = ga as usize;
    let nt = core::ptr::read_unaligned((base + 0x3c) as *const u32) as usize;
    let image_size = core::ptr::read_unaligned((base + nt + 24 + 56) as *const u32) as usize;
    let page = alloc_near(base, image_size);
    let hooks = [h_set_text as *const () as usize, h_settext1 as *const () as usize, h_settext2 as *const () as usize];
    let mut out = format!("rtl: TMP_Text + {} subclasses, align={}", classes.len() - 1, ALIGN);
    for i in 0..3 {
        if targets[i] == 0 {
            continue;
        }
        ORIG[i] = targets[i];
        let c = redirect(base, targets[i], hooks[i], &infos, &classes, if page != 0 { page + i * 16 } else { 0 });
        out += &format!("; hook{i} {:#x}: methodinfo {} vtable {} table {} calls {}", targets[i] - base, c[0], c[1], c[2], c[3]);
    }
    TMP_TEXT = tmp as usize;
    API = Some(a);
    out
}

/// Test entry (no game needed): install into an initialised GameAssembly; the report goes into `buf`.
#[no_mangle]
pub unsafe extern "C" fn tirgumim_rtl_selftest(ga: Handle, buf: *mut u8, cap: usize) -> usize {
    let ga = if ga.is_null() { GetModuleHandleW(crate::wide("GameAssembly.dll").as_ptr()) } else { ga };
    let r = install(ga);
    let n = r.len().min(cap);
    core::ptr::copy_nonoverlapping(r.as_ptr(), buf, n);
    n
}

/// Test entry: the TextMeshPro order of a UTF-16 string.
#[no_mangle]
pub unsafe extern "C" fn tirgumim_rtl_text(s: *const u16, n: usize, out: *mut u16, cap: usize) -> usize {
    let r = rtl::tmp_rtl(core::slice::from_raw_parts(s, n));
    let k = r.len().min(cap);
    core::ptr::copy_nonoverlapping(r.as_ptr(), out, k);
    r.len()
}

#[cfg(test)]
mod tests {
    use super::*;
    fn w(s: &str) -> Vec<u16> {
        s.encode_utf16().collect()
    }
    fn s16(v: &[u16]) -> String {
        String::from_utf16_lossy(v)
    }
    fn k(s: &str) -> String {
        format!("{:016x}", sha::key_str(s))
    }
    fn upper(s: &[u16]) -> Vec<u16> {
        String::from_utf16_lossy(s).to_uppercase().encode_utf16().collect()
    }

    /// labels.txt as build.py writes it, from (English, Hebrew) pairs in English order.
    fn labels_file(pairs: &[(&str, &str)]) -> String {
        let mut pairs = pairs.to_vec();
        pairs.sort();
        let exact: HashSet<String> = pairs.iter().map(|(en, _)| k(en)).collect();
        let mut out: String = pairs.iter().map(|(en, he)| format!("{}\t{}\n", k(en), escape(he))).collect();
        let mut up = HashSet::new();
        for (en, he) in &pairs {
            let u = k(&en.to_uppercase());
            if !exact.contains(&u) && up.insert(u.clone()) {
                out += &format!("^{u}\t{}\n", escape(he));
            }
        }
        out
    }

    #[test]
    fn labels() {
        let l = Labels::parse(&labels_file(&[("Rating", "דירוג"), ("Search filters", "מסנני חיפוש"), ("Two\nlines", "שתי\nשורות")]));
        let f = |s: &str| l.label_for(&w(s)).map(|v| s16(&v));
        assert_eq!(f("Rating").as_deref(), Some("דירוג"));
        assert_eq!(f("RATING").as_deref(), Some("דירוג"));
        assert_eq!(f("Two\nlines").as_deref(), Some("שתי\nשורות"));
        assert_eq!(f("  Rating: ").as_deref(), Some("  דירוג: "));
        assert_eq!(f("<b>Rating</b>\n15").as_deref(), Some("<b>דירוג</b>\n15"));
        assert_eq!(f("<color=#fff>SEARCH FILTERS</color>").as_deref(), Some("<color=#fff>מסנני חיפוש</color>"));
        assert_eq!(f("Ratings"), None);
        assert_eq!(f("rating"), None);
        assert_eq!(f("RATINg"), None);
        // no English in the file, and a line that is not a key is ignored
        let file = labels_file(&[("Rating", "דירוג")]);
        assert!(!file.contains("Rating"));
        assert_eq!(Labels::parse("Rating\tדירוג\n").label_for(&w("Rating")), None);
    }

    #[test]
    fn skeletons() {
        // the same cases and keys as tools/sources.py skeleton() + common.H() (checked in Python)
        let c = |t: &str| {
            let v = w(t);
            let (sk, holes) = skeleton(&v);
            (s16(&sk), holes.iter().map(|h| s16(h)).collect::<Vec<_>>(), format!("{:016x}", sha::key(&sk)))
        };
        let (sk, h, key) = c("Scored 12 points in 3 games for the EU side, best — 19.");
        assert_eq!(sk, "Scored {} points in {} games for the {} side, best — {}.");
        assert_eq!(h, ["12", "3", "EU", "19"]);
        assert_eq!(key, "3aacf3e51d940fe5");
        let (sk, h, key) = c("Has 2 308 XP (lvl 10), since 17.02.2019, 248u wins, K/D 1.47.");
        assert_eq!(sk, "Has {} {} (lvl {}), since {}, {} wins, K/D {}.");
        assert_eq!(h, ["2 308", "XP", "10", "17.02.2019", "248u", "1.47"]);
        assert_eq!(key, "c15d0079342d48c3");
        let (sk, h, key) = c("x32 Jan CS2 1.5. 3.");
        assert_eq!((sk.as_str(), h), ("x32 Jan CS2 {}. {}.", vec!["1.5".to_string(), "3".to_string()]));
        assert_eq!(key, "52948cef7cf3343a");
        let (sk, h, key) = c(" A1 AB ABCDE 7 8x 9.9.9 ");
        assert_eq!((sk.as_str(), h), (" A1 {} ABCDE {} ", vec!["AB".to_string(), "7 8x 9.9.9".to_string()]));
        assert_eq!(key, "afa63b429f136254");
    }

    #[test]
    fn bios() {
        // an invented template (the real ones exist only as keys): holes in text order, {N} in the Hebrew
        let tpl = "Scored {} points in {} games for the {} side, best — {}.";
        let he = "קלע {0} נקודות ב-{1} משחקים בצד {2}, השיא: {3}.";
        let file = format!(
            "{}\tמאיה משחקת כ-rifler.\\nהיא מובילה.\n*\t{}\t{he}\n*\tnot-a-key\tx\n",
            k("Maya plays as a rifler.\nShe leads."),
            k(tpl)
        );
        let b = Bios::parse(&file);
        assert_eq!(b.counts(), (1, 1));
        let f = |s: &str| b.bio_for(&w(s)).map(|v| s16(&v));
        assert_eq!(f("Maya plays as a rifler.\nShe leads.").as_deref(), Some("מאיה משחקת כ-rifler.\nהיא מובילה."));
        assert_eq!(f("Maya plays as a rifler."), None); // whole text only
        let s = "Scored 4 484 points in 11259 games for the EU side, best — 19.";
        assert_eq!(f(s).as_deref(), Some("קלע 4 484 נקודות ב-11259 משחקים בצד EU, השיא: 19."));
        assert_eq!(f(&s.replace("EU", "OCE")).as_deref(), Some("קלע 4 484 נקודות ב-11259 משחקים בצד OCE, השיא: 19."));
        assert_eq!(f(&s.replace("11259", "05i7")).map(|v| v.contains("ב-05i7 ")), Some(true));
        assert_eq!(f(&format!(" {s}\n")).map(|v| v.starts_with(" קלע 4 484") && v.ends_with(": 19.\n")), Some(true));
        assert_eq!(f(&s.replace("games", "maps")), None);
        assert_eq!(f(&format!("{s} More.")), None);
        assert_eq!(f(&s.replace("for the EU side", "for the Europe side")), None); // a hole is not a word
        assert_eq!(f(&s.replace(" 11259 ", " ")), None); // a missing hole
        assert_eq!(f(""), None);
        assert_eq!(f("   "), None);
    }

    #[test]
    fn keep_and_textlog() {
        let kp = Keep::parse(&format!("{}\n{}\r\nVaitzman\n", k("Vaitzman \"Maya\""), k("@CS2News")));
        assert!(kp.has(&w("Vaitzman \"Maya\"")));
        assert!(kp.has(&w("  @CS2News\n")));
        assert!(!kp.has(&w("Vaitzman"))); // not a key line
        assert_eq!(log_line(Some(&kp), &w("@CS2News")), None);
        assert_eq!(log_line(Some(&kp), &w("Recent results")).as_deref(), Some("Recent results"));
        assert_eq!(log_line(Some(&kp), &w("Two\nlines")).as_deref(), Some("Two\\nlines"));
        assert_eq!(log_line(None, &w("1:0")), None);
        assert_eq!(log_line(None, &w("K/D 1.47")).as_deref(), Some("K/D 1.47")); // two Latin letters are enough
    }

    // ---- the hashed files against the plain (English-keyed, old) lookup, on the real pack data ----
    // build.py writes work/pack/files/tirgumim/he/{labels,bios,keep}.txt (shipped, hashed) and the same entries
    // with English keys into work/plain/ (local only). These tests run when both exist (after a build).

    fn work(p: &str) -> Option<String> {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../work").join(p);
        std::fs::read_to_string(path).ok()
    }

    /// The old text lookup: exact English map, and the upper-case map built from it (first label wins).
    struct OldLabels {
        exact: HashMap<Vec<u16>, Vec<u16>>,
        up: HashMap<Vec<u16>, Vec<u16>>,
    }
    impl OldLabels {
        fn parse(txt: &str) -> OldLabels {
            let (mut exact, mut up) = (HashMap::new(), HashMap::new());
            for line in txt.lines() {
                if let Some((en, he)) = line.split_once('\t') {
                    let (kk, v) = (w16(en), w16(he));
                    up.entry(upper(&kk)).or_insert_with(|| v.clone());
                    exact.insert(kk, v);
                }
            }
            OldLabels { exact, up }
        }
        fn lookup(&self, t: &[u16]) -> Option<Vec<u16>> {
            if let Some(v) = self.exact.get(t) {
                return Some(v.clone());
            }
            let lower = t.iter().any(|&c| (b'a' as u16..=b'z' as u16).contains(&c));
            let up = t.iter().any(|&c| (b'A' as u16..=b'Z' as u16).contains(&c));
            if up && !lower { self.up.get(t).cloned() } else { None }
        }
    }

    #[test]
    fn real_labels_hashed_equals_plain() {
        let (Some(plain), Some(hashed)) = (work("plain/labels.txt"), work("pack/files/tirgumim/he/labels.txt")) else {
            eprintln!("skipped: run tools/build.py first (work/plain, work/pack)");
            return;
        };
        let old = OldLabels::parse(&plain);
        let new = Labels::parse(&hashed);
        assert!(!hashed.contains("Rating\t") && new.exact.len() == old.exact.len(), "hashed file: one key per label");
        let mut n = 0;
        for en in old.exact.keys() {
            let e = s16(en);
            let u = s16(&upper(en));
            for t in [e.clone(), u.clone(), format!("<b>{e}</b>\n15"), format!("  {e}: "), format!("{u}\n{e}"),
                      format!("<color=#fff>{u}</color>"), format!("{e}s"), e.to_lowercase()] {
                let t = w(&t);
                assert_eq!(new.label_for(&t), label_for_with(&t, &|s| old.lookup(s)), "{}", s16(&t));
                n += 1;
            }
        }
        assert!(n > 5000, "{n} lookups");
    }

    #[test]
    fn real_bios_hashed_equals_plain() {
        let (Some(plain), Some(faceit), Some(hashed)) =
            (work("plain/bios.txt"), work("plain/faceit.txt"), work("pack/files/tirgumim/he/bios.txt"))
        else {
            eprintln!("skipped: run tools/build.py first (work/plain, work/pack)");
            return;
        };
        let new = Bios::parse(&hashed);
        let mut n = 0;
        for line in plain.lines() {
            let (en, he) = line.split_once('\t').unwrap();
            assert_eq!(new.bio_for(&w16(en)).map(|v| s16(&v)), Some(unescape(he)), "{en}");
            n += 1;
        }
        assert_eq!(new.counts().0, n);
        // FaceIt bios of today's default.emdb, Hebrew from tools/sources.py faceit_he (which gives what the old
        // English template lines gave): every one through the hashed skeleton templates
        let mut m = 0;
        for line in faceit.lines() {
            let (en, he) = line.split_once('\t').unwrap();
            assert_eq!(new.bio_for(&w16(en)).map(|v| s16(&v)), Some(unescape(he)), "{en}");
            let spaced = format!(" {}\n", unescape(en));
            assert_eq!(new.bio_for(&w(&spaced)).map(|v| s16(&v)), Some(format!(" {}\n", unescape(he))));
            m += 1;
        }
        assert!(n > 1000 && m > 4000, "{n} bios, {m} FaceIt bios");
    }

    /// Cost of the hashed lookups per displayed text: `cargo test --release -- --ignored --nocapture lookup_cost`
    #[test]
    #[ignore]
    fn lookup_cost() {
        let (Some(plain), Some(lab), Some(bio)) =
            (work("plain/labels.txt"), work("pack/files/tirgumim/he/labels.txt"), work("pack/files/tirgumim/he/bios.txt"))
        else {
            return;
        };
        let (labels, bios) = (Labels::parse(&lab), Bios::parse(&bio));
        let mut texts: Vec<Vec<u16>> = plain.lines().map(|l| w16(l.split('\t').next().unwrap())).collect();
        texts.extend(["12", "1:0", "Mirage", "<b>Rating</b>\n15", "Has no label at all, a longer sentence of text."].map(w));
        let t0 = std::time::Instant::now();
        let mut hits = 0;
        let rounds = 200;
        for _ in 0..rounds {
            for t in &texts {
                hits += bios.bio_for(t).is_some() as usize + labels.label_for(t).is_some() as usize;
            }
        }
        let per = t0.elapsed().as_secs_f64() * 1e6 / (rounds * texts.len()) as f64;
        eprintln!("{per:.2} us per text (bio + label lookup), {hits} hits");
    }

    #[test]
    fn real_keep_hashed_equals_plain() {
        let (Some(plain), Some(hashed)) = (work("plain/keep.txt"), work("pack/files/tirgumim/he/keep.txt")) else {
            eprintln!("skipped: run tools/build.py first (work/plain, work/pack)");
            return;
        };
        let new = Keep::parse(&hashed);
        let old: HashSet<Vec<u16>> = plain.lines().filter(|l| !l.is_empty()).map(w16).collect();
        for en in &old {
            assert!(new.has(en), "{}", s16(en));
            let spaced = w(&format!(" {} ", s16(en)));
            assert_eq!(new.has(&spaced), old.contains(&spaced) || old.contains(&w(s16(&spaced).trim())));
            assert_eq!(log_line(Some(&new), en), None);
        }
        assert!(old.len() > 10000, "{} kept texts", old.len());
    }
}
