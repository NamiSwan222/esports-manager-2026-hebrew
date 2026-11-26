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
use crate::rtl;
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

/// `labels=<file>` in redirect.cfg: UTF-8 lines `English<TAB>Hebrew` (`\n`, `\t`, `\\` escaped).
static mut LABELS: Option<HashMap<Vec<u16>, Vec<u16>>> = None;
/// `-tirgumim_textlog`: every distinct text without Hebrew set on a TextMeshPro component goes to
/// %TEMP%\tirgumim_text.log (one per line, escaped like the labels file), to find untranslated text.
static mut TEXTLOG: bool = false;
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

pub unsafe fn load_labels(path: &str) -> usize {
    let Ok(txt) = std::fs::read_to_string(path) else { return 0 };
    let mut m = HashMap::new();
    for line in txt.lines() {
        if let Some((en, he)) = line.split_once('\t') {
            if !en.is_empty() && !he.is_empty() {
                m.insert(unescape(en).encode_utf16().collect(), unescape(he).encode_utf16().collect());
            }
        }
    }
    let n = m.len();
    LABELS = Some(m);
    n
}

pub unsafe fn enable_textlog() {
    TEXTLOG = true;
}

fn text_log(text: &[u16]) {
    let s = String::from_utf16_lossy(text);
    if s.chars().filter(|c| c.is_ascii_alphabetic()).count() < 2 {
        return;
    }
    let h = hash(text);
    let mut g = LOGGED.lock().unwrap();
    if !g.get_or_insert_with(HashSet::new).insert(h) {
        return;
    }
    use std::io::Write;
    let p = std::env::temp_dir().join("tirgumim_text.log");
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(p) {
        let _ = writeln!(f, "{}", escape(&s));
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
    if !rtl::has_rtl(text) {
        // exact English UI labels shown through TextMeshPro: Hebrew for display only (code keys stay English)
        if let Some(he) = LABELS.as_ref().and_then(|m| m.get(text)) {
            let ns = (a.string_new_utf16)(he.as_ptr(), he.len() as i32);
            if !ns.is_null() {
                s = ns;
                text = he.as_slice();
            }
        } else if TEXTLOG {
            text_log(text);
        }
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

/// A page for jump stubs within Ã‚Â±2 GB of the module (for rel32 calls).
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
