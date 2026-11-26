//! Logical Hebrew text -> the order TextMeshPro needs when `isRightToLeftText` is on.
//!
//! TextMeshPro has no bidi algorithm. With `isRightToLeftText` it places the characters of the string
//! one after another from the right edge leftwards and wraps lines in string order. So for a
//! right-to-left paragraph the string must be "the visual line read from right to left": Hebrew and
//! neutrals stay in logical order, every left-to-right run (Latin words, numbers, "12/05/2026", "3-1",
//! "50%") is reversed in place, and brackets inside right-to-left text are mirrored. Line order of
//! wrapped text then stays right because TextMeshPro still wraps from the start of the string.
//!
//! This is the Unicode bidi algorithm (UAX #9) reduced to what UI text needs: paragraph level 1
//! (right-to-left), no explicit embeddings (embedding/isolate controls are removed; LRM/RLM count as L/R), rules W1-W7, N0-N2,
//! I2, L2 for levels 1 and 2. TextMeshPro rich-text tags are kept as they are and do not take part;
//! a tag pair inside a reversed run is swapped so it still wraps the same characters.

const R: u8 = 0;
const L: u8 = 1;
const EN: u8 = 2;
const ES: u8 = 3;
const ET: u8 = 4;
const CS: u8 = 5;
const NSM: u8 = 6;
const ON: u8 = 7; // WS, ON and everything else neutral
const TAG: u8 = 8;
const BR: u8 = 9; // paragraph separator: \n, \r, <br>

pub fn is_rtl_char(c: u32) -> bool {
    matches!(c, 0x0590..=0x08FF | 0xFB1D..=0xFDFF | 0xFE70..=0xFEFF)
}

fn is_nsm(c: u32) -> bool {
    matches!(c, 0x0591..=0x05BD | 0x05BF | 0x05C1..=0x05C2 | 0x05C4..=0x05C5 | 0x05C7 | 0x0300..=0x036F | 0x064B..=0x065F | 0x0670)
}

fn is_bidi_control(c: u32) -> bool {
    matches!(c, 0x061C | 0x202A..=0x202E | 0x2066..=0x2069) // LRM/RLM stay: they act as strong L/R
}

fn class(c: u32) -> u8 {
    if is_nsm(c) {
        return NSM;
    }
    if is_rtl_char(c) || c == 0x200F {
        return R;
    }
    if c == 0x200E {
        return L;
    }
    match c {
        0x30..=0x39 | 0xB2 | 0xB3 | 0xB9 | 0x2070..=0x2079 | 0x2080..=0x2089 | 0xFF10..=0xFF19 => EN,
        0x2B | 0x2D | 0x2212 | 0xFB29 | 0xFE62 | 0xFE63 | 0xFF0B | 0xFF0D => ES,
        0x23..=0x25 | 0xA2..=0xA5 | 0xB0 | 0xB1 | 0x2030..=0x2034 | 0x20A0..=0x20CF | 0x2103 | 0x2109 => ET,
        0x2C | 0x2E | 0x2F | 0x3A | 0xA0 | 0x202F | 0xFF0C | 0xFF0E | 0xFF0F | 0xFF1A => CS,
        _ => match char::from_u32(c) {
            Some(ch) if ch.is_alphabetic() => L,
            _ => ON,
        },
    }
}

fn mirror(c: u32) -> u32 {
    match c {
        0x28 => 0x29,
        0x29 => 0x28,
        0x5B => 0x5D,
        0x5D => 0x5B,
        0x7B => 0x7D,
        0x7D => 0x7B,
        0x3C => 0x3E,
        0x3E => 0x3C,
        0xAB => 0xBB,
        0xBB => 0xAB,
        0x2039 => 0x203A,
        0x203A => 0x2039,
        0x2264 => 0x2265,
        0x2265 => 0x2264,
        _ => c,
    }
}

/// A TextMeshPro rich-text tag starting at `i` (`<b>`, `</color>`, `<size=-5>`, `<#ff0000>`, `<br>`): its end.
fn tag_end(s: &[u32], i: usize) -> Option<usize> {
    let next = *s.get(i + 1)?;
    let ok = matches!(char::from_u32(next), Some(ch) if ch.is_ascii_alphabetic() || ch == '/' || ch == '#');
    if !ok {
        return None;
    }
    let mut j = i + 1;
    while j < s.len() && j - i < 128 {
        match s[j] {
            0x3E => return Some(j + 1),
            0x3C | 0x0A | 0x0D => return None,
            _ => j += 1,
        }
    }
    None
}

fn tag_name(t: &[u32]) -> (bool, String) {
    let close = t.get(1) == Some(&0x2F);
    let name: String = t[if close { 2 } else { 1 }..]
        .iter()
        .map(|&c| char::from_u32(c).unwrap_or(' '))
        .take_while(|ch| ch.is_ascii_alphanumeric() || *ch == '-' || *ch == '#')
        .collect::<String>()
        .to_ascii_lowercase();
    (close, if name.starts_with('#') { "color".into() } else { name })
}

struct Tok {
    s: Vec<u32>,
    t: u8,
    level: u8,
}

pub fn has_rtl(s: &[u16]) -> bool {
    s.iter().any(|&c| is_rtl_char(c as u32))
}

/// Logical UTF-16 text -> TextMeshPro right-to-left order. Text without right-to-left letters is returned
/// unchanged (apart from bidi controls being removed only when there is Hebrew).
pub fn tmp_rtl(input: &[u16]) -> Vec<u16> {
    if !has_rtl(input) {
        return input.to_vec();
    }
    let s: Vec<u32> = char::decode_utf16(input.iter().copied())
        .map(|r| r.map(|c| c as u32).unwrap_or(0xFFFD))
        .filter(|&c| !is_bidi_control(c))
        .collect();
    // tokens: one per character, one per tag
    let mut toks: Vec<Tok> = vec![];
    let mut i = 0;
    while i < s.len() {
        if s[i] == 0x3C {
            if let Some(e) = tag_end(&s, i) {
                let t = s[i..e].to_vec();
                let ty = if tag_name(&t).1 == "br" { BR } else { TAG };
                toks.push(Tok { s: t, t: ty, level: 1 });
                i = e;
                continue;
            }
        }
        let ty = if s[i] == 0x0A || s[i] == 0x0D || s[i] == 0x2028 || s[i] == 0x2029 { BR } else { class(s[i]) };
        toks.push(Tok { s: vec![s[i]], t: ty, level: 1 });
        i += 1;
    }
    let mut out: Vec<u32> = Vec::with_capacity(s.len());
    let mut start = 0;
    while start <= toks.len() {
        let end = toks[start..].iter().position(|t| t.t == BR).map_or(toks.len(), |p| start + p);
        paragraph(&mut toks[start..end], &mut out);
        if end < toks.len() {
            out.extend_from_slice(&toks[end].s);
        }
        start = end + 1;
    }
    let mut r = Vec::with_capacity(out.len());
    for c in out {
        let mut b = [0u16; 2];
        r.extend_from_slice(char::from_u32(c).unwrap_or('\u{FFFD}').encode_utf16(&mut b));
    }
    r
}

fn paragraph(toks: &mut [Tok], out: &mut Vec<u32>) {
    // indexes of the characters (tags are ignored like BN)
    let ix: Vec<usize> = (0..toks.len()).filter(|&k| toks[k].t != TAG).collect();
    let mut t: Vec<u8> = ix.iter().map(|&k| toks[k].t).collect();
    let n = t.len();
    // W1: NSM takes the previous type (sos is R)
    for k in 0..n {
        if t[k] == NSM {
            t[k] = if k == 0 { R } else { t[k - 1] };
        }
    }
    // W2 has no effect without AL; W3 likewise. W4: single ES between EN, single CS between EN
    for k in 1..n.saturating_sub(1) {
        if (t[k] == ES || t[k] == CS) && t[k - 1] == EN && t[k + 1] == EN {
            t[k] = EN;
        }
    }
    // W5: ET sequences next to EN become EN
    let mut k = 0;
    while k < n {
        if t[k] == ET {
            let e = (k..n).find(|&j| t[j] != ET).unwrap_or(n);
            if (k > 0 && t[k - 1] == EN) || (e < n && t[e] == EN) {
                t[k..e].iter_mut().for_each(|x| *x = EN);
            }
            k = e;
        } else {
            k += 1;
        }
    }
    // W6: remaining separators and terminators are neutral
    for x in t.iter_mut() {
        if matches!(*x, ES | ET | CS) {
            *x = ON;
        }
    }
    // W7: EN after a strong L (looking back, sos = R) is L
    let mut last = R;
    for x in t.iter_mut() {
        match *x {
            L | R => last = *x,
            EN if last == L => *x = L,
            _ => {}
        }
    }
    // N0: paired brackets take the direction of their content ("Team (They Don't Know) היא" stays one run)
    let chars: Vec<u32> = ix.iter().map(|&k| toks[k].s[0]).collect();
    let mut open: Vec<(u32, usize)> = vec![];
    let mut pairs = vec![];
    for j in 0..n {
        if t[j] != ON {
            continue;
        }
        match chars[j] {
            0x28 => open.push((0x29, j)),
            0x5B => open.push((0x5D, j)),
            0x7B => open.push((0x7D, j)),
            c @ (0x29 | 0x5D | 0x7D) => {
                if let Some(p) = open.iter().rposition(|x| x.0 == c) {
                    pairs.push((open[p].1, j));
                    open.truncate(p);
                }
            }
            _ => {}
        }
        if open.len() > 63 {
            break;
        }
    }
    pairs.sort();
    for (o, c) in pairs {
        let inside = &t[o + 1..c];
        let d = if inside.iter().any(|&x| x == R || x == EN) {
            R
        } else if inside.contains(&L) {
            let before = (0..o).rev().find_map(|j| match t[j] {
                L => Some(L),
                R | EN => Some(R),
                _ => None,
            });
            before.unwrap_or(R)
        } else {
            continue;
        };
        t[o] = d;
        t[c] = d;
    }
    // N1/N2: neutral runs between same-direction strong types take it (EN counts as R), else R (embedding)
    let strong = |x: u8| if x == L { L } else { R };
    let mut k = 0;
    while k < n {
        if t[k] == ON {
            let e = (k..n).find(|&j| t[j] != ON).unwrap_or(n);
            let before = if k == 0 { R } else { strong(t[k - 1]) };
            let after = if e == n { R } else { strong(t[e]) };
            let d = if before == L && after == L { L } else { R };
            t[k..e].iter_mut().for_each(|x| *x = d);
            k = e;
        } else {
            k += 1;
        }
    }
    // I2 at paragraph level 1: L and EN go to level 2
    for (j, &k) in ix.iter().enumerate() {
        toks[k].level = if t[j] == R { 1 } else { 2 };
    }
    // tags: level 2 only inside a level-2 run (both neighbouring characters at level 2)
    for k in 0..toks.len() {
        if toks[k].t == TAG {
            let prev = toks[..k].iter().rev().find(|x| x.t != TAG).map_or(1, |x| x.level);
            let next = toks[k + 1..].iter().find(|x| x.t != TAG).map_or(1, |x| x.level);
            toks[k].level = if prev == 2 && next == 2 { 2 } else { 1 };
        }
    }
    // L2 as TextMeshPro needs it: level-1 tokens in place (mirrored), level-2 runs reversed
    let mut k = 0;
    while k < toks.len() {
        if toks[k].level == 1 {
            if toks[k].t == TAG {
                out.extend_from_slice(&toks[k].s);
            } else {
                out.push(mirror(toks[k].s[0]));
            }
            k += 1;
            continue;
        }
        let e = (k..toks.len()).find(|&j| toks[j].level != 2).unwrap_or(toks.len());
        reversed_run(&toks[k..e], out);
        k = e;
    }
}

/// A left-to-right run, reversed. Matched tag pairs swap places so they wrap the same characters;
/// an unmatched opening tag goes to the start and an unmatched closing tag to the end.
fn reversed_run(run: &[Tok], out: &mut Vec<u32>) {
    let mut swap: Vec<Option<usize>> = vec![None; run.len()];
    let mut stack: Vec<(usize, String)> = vec![];
    let mut openers = vec![];
    let mut closers = vec![];
    for (k, t) in run.iter().enumerate() {
        if t.t != TAG {
            continue;
        }
        let (close, name) = tag_name(&t.s);
        if !close {
            stack.push((k, name));
        } else if let Some(p) = stack.iter().rposition(|(_, n)| *n == name) {
            let (o, _) = stack.remove(p);
            swap[o] = Some(k);
            swap[k] = Some(o);
        } else {
            closers.push(k);
        }
    }
    openers.extend(stack.into_iter().map(|(k, _)| k));
    for &k in &openers {
        out.extend_from_slice(&run[k].s);
    }
    for k in (0..run.len()).rev() {
        if openers.contains(&k) || closers.contains(&k) {
            continue;
        }
        let src = swap[k].unwrap_or(k);
        out.extend_from_slice(&run[src].s);
    }
    for &k in &closers {
        out.extend_from_slice(&run[k].s);
    }
}

#[cfg(test)]
mod tests {
    use super::tmp_rtl;

    fn f(s: &str) -> String {
        String::from_utf16(&tmp_rtl(&s.encode_utf16().collect::<Vec<_>>())).unwrap()
    }

    #[test]
    fn hebrew_only_is_unchanged() {
        assert_eq!(f("משחק חדש"), "משחק חדש");
        assert_eq!(f("שורה אחת\nשורה שתיים"), "שורה אחת\nשורה שתיים");
    }

    #[test]
    fn latin_text_untouched() {
        assert_eq!(f("Maya (2026) <b>x</b>"), "Maya (2026) <b>x</b>");
    }

    #[test]
    fn ltr_runs_reversed() {
        assert_eq!(f("שלום Maya!"), "שלום ayaM!");
        assert_eq!(f("מאמן Maya Smith"), "מאמן htimS ayaM");
        assert_eq!(f("Maya מאמנת"), "ayaM מאמנת");
        assert_eq!(f("ניצחון 3-1"), "ניצחון 1-3");
        assert_eq!(f("ב-12/05/2026 בערב"), "ב-6202/50/21 בערב");
        assert_eq!(f("עלייה של 50%"), "עלייה של %05");
        assert_eq!(f("עלות 1,000 ₪"), "עלות 000,1 ₪");
        assert_eq!(f("Maya 2 שחקנית"), "2 ayaM שחקנית");
    }

    #[test]
    fn brackets_mirror_in_rtl_only() {
        assert_eq!(f("שחקן (ותיק)"), "שחקן )ותיק(");
        assert_eq!(f("שחקן (Maya)"), "שחקן )ayaM(");
        // brackets around Latin after Latin belong to the Latin run (UAX #9 N0)
        assert_eq!(f("Team TKDE (They Don't Know) היא"), ")wonK t'noD yehT( EDKT maeT היא");
        assert_eq!(f("קבוצת Counter-Strike 2 (CS2) מקצוענית"), "קבוצת )2SC( 2 ekirtS-retnuoC מקצוענית");
    }

    #[test]
    fn tags_stay_paired() {
        assert_eq!(f("מינוי <b>Maya Smith</b> אושר"), "מינוי <b>htimS ayaM</b> אושר");
        // a tag that opens inside a Latin run and closes after it: approximated (whole run formatted)
        assert_eq!(f("שם: Maya <b>Smith</b>"), "שם: <b>htimS ayaM</b>");
        assert_eq!(f("<color=red>Maya</color> שלום"), "<color=red>ayaM</color> שלום");
        assert_eq!(f("דירוג <font-weight=700>ERS</font-weight> עם 5"), "דירוג <font-weight=700>SRE</font-weight> עם 5");
        assert_eq!(f("המשך<br><size=-5>בתור Maya"), "המשך<br><size=-5>בתור ayaM");
    }

    #[test]
    fn paragraphs_independent_and_controls_removed() {
        assert_eq!(f("\u{2067}שלום Maya\u{2069}\nTeam A"), "שלום ayaM\nA maeT");
        assert_eq!(f("בין KDA,\u{200F} K/D ודירוג"), "בין ADK,\u{200F} D/K ודירוג");
    }

    #[test]
    fn numbers_keep_digit_order_after_reversal() {
        // the reversed string, laid out from the right, shows "25" as 2 then 5 left to right
        assert_eq!(f("נקודות: 25"), "נקודות: 52");
    }
}
