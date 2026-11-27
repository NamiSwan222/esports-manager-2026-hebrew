//! English dates built at run time (`DateTime.ToString("dddd")`, `"dd MMM yyyy"`, en-US long dates) -> Hebrew,
//! enabled by `dates=<file>` in redirect.cfg. The file (translation/he/dates.txt, format described there) holds
//! the Hebrew weekday and month names and the date shapes; only a whole shape (names next to day/year numbers)
//! is rewritten, so a team called "May" or a word like "March" in a sentence stays as it is.

#[derive(Clone, Copy, PartialEq, Debug)]
enum Tok {
    Lit(u16),
    Weekday,
    Month,
    Day,
    Year,
    End,
}

#[derive(Clone, PartialEq, Debug)]
enum Out {
    Lit(u16),
    Weekday { short: bool },
    Day,
    Year,
    /// short: Some(true/false) = that form, None = the form of the English month; prefix: "in" before it
    Month { short: Option<bool>, prefix: bool },
}

#[derive(Default)]
pub struct Dates {
    weekdays: Vec<(Vec<u16>, usize)>,     // English name -> index, longest first
    months: Vec<(Vec<u16>, usize, bool)>, // English name -> index, is a short form; longest first
    he_weekdays: Vec<(Vec<u16>, Vec<u16>)>,
    he_months: Vec<(Vec<u16>, Vec<u16>)>,
    prefix: Vec<u16>,
    shapes: Vec<(Vec<Tok>, Vec<Out>)>,
}

#[derive(Default)]
struct Caps<'a> {
    weekday: usize,
    month: usize,
    month_short: bool,
    day: u32,
    year: &'a [u16],
}

fn w(s: &str) -> Vec<u16> {
    s.encode_utf16().collect()
}

fn is_digit(c: u16) -> bool {
    (b'0' as u16..=b'9' as u16).contains(&c)
}

fn is_alpha(c: u16) -> bool {
    char::from_u32(c as u32).is_some_and(|c| c.is_alphabetic())
}

fn is_space(c: u16) -> bool {
    c == 0x20 || c == 0xa0
}

fn parse_en(s: &str) -> Vec<Tok> {
    let mut v = vec![];
    let mut rest = s;
    while !rest.is_empty() {
        let tok = [("{W}", Tok::Weekday), ("{M}", Tok::Month), ("{d}", Tok::Day), ("{y}", Tok::Year), ("{$}", Tok::End)]
            .into_iter()
            .find(|(k, _)| rest.starts_with(k));
        if let Some((k, t)) = tok {
            v.push(t);
            rest = &rest[k.len()..];
        } else {
            let c = rest.chars().next().unwrap();
            let mut b = [0u16; 2];
            v.extend(c.encode_utf16(&mut b).iter().map(|&u| Tok::Lit(u)));
            rest = &rest[c.len_utf8()..];
        }
    }
    v
}

fn parse_he(s: &str) -> Vec<Out> {
    let keys = [
        ("{W}", Out::Weekday { short: false }),
        ("{w}", Out::Weekday { short: true }),
        ("{d}", Out::Day),
        ("{y}", Out::Year),
        ("{inM?}", Out::Month { short: None, prefix: true }),
        ("{inM}", Out::Month { short: Some(false), prefix: true }),
        ("{inm}", Out::Month { short: Some(true), prefix: true }),
        ("{M?}", Out::Month { short: None, prefix: false }),
        ("{M}", Out::Month { short: Some(false), prefix: false }),
        ("{m}", Out::Month { short: Some(true), prefix: false }),
    ];
    let mut v = vec![];
    let mut rest = s;
    'outer: while !rest.is_empty() {
        for (k, o) in keys.iter() {
            if rest.starts_with(k) {
                v.push(o.clone());
                rest = &rest[k.len()..];
                continue 'outer;
            }
        }
        let c = rest.chars().next().unwrap();
        let mut b = [0u16; 2];
        v.extend(c.encode_utf16(&mut b).iter().map(|&u| Out::Lit(u)));
        rest = &rest[c.len_utf8()..];
    }
    v
}

impl Dates {
    pub fn parse(txt: &str) -> Dates {
        let mut d = Dates::default();
        for line in txt.lines() {
            if line.starts_with('#') {
                continue;
            }
            let f: Vec<&str> = line.split('\t').collect();
            match f.as_slice() {
                ["weekday", en, he, he_short] => {
                    let i = d.he_weekdays.len();
                    d.weekdays.extend(en.split('|').filter(|s| !s.is_empty()).map(|s| (w(s), i)));
                    d.he_weekdays.push((w(he), w(he_short)));
                }
                ["month", en, he, he_short] => {
                    let i = d.he_months.len();
                    d.months.extend(en.split('|').filter(|s| !s.is_empty()).enumerate().map(|(k, s)| (w(s), i, k > 0)));
                    d.he_months.push((w(he), w(he_short)));
                }
                ["in", p] => d.prefix = w(p),
                ["shape", en, he] if !en.is_empty() => d.shapes.push((parse_en(en), parse_he(he))),
                _ => {}
            }
        }
        d.weekdays.sort_by_key(|(n, _)| std::cmp::Reverse(n.len()));
        d.months.sort_by_key(|(n, _, _)| std::cmp::Reverse(n.len()));
        d
    }

    pub fn len(&self) -> usize {
        self.shapes.len()
    }

    /// The end of a name from `names` at `t[i..]` (not followed by a letter), and its entry.
    fn name<'a, T>(names: &'a [(Vec<u16>, T)], t: &[u16], i: usize) -> Option<(usize, &'a T)> {
        names.iter().find_map(|(n, x)| {
            let e = i + n.len();
            (t.get(i..e) == Some(n.as_slice()) && !t.get(e).is_some_and(|&c| is_alpha(c))).then_some((e, x))
        })
    }

    fn month_at(&self, t: &[u16], i: usize) -> Option<(usize, usize, bool)> {
        self.months.iter().find_map(|(n, k, short)| {
            let e = i + n.len();
            (t.get(i..e) == Some(n.as_slice()) && !t.get(e).is_some_and(|&c| is_alpha(c))).then_some((e, *k, *short))
        })
    }

    /// Match `shape` at `t[i..]`: the end and the captured parts.
    fn match_at<'a>(&self, shape: &[Tok], t: &'a [u16], i: usize) -> Option<(usize, Caps<'a>)> {
        let mut c = Caps::default();
        let mut p = i;
        for tok in shape {
            match *tok {
                Tok::Lit(ch) => {
                    let x = *t.get(p)?;
                    if !(x == ch || (ch == 0x20 && is_space(x))) {
                        return None;
                    }
                    p += 1;
                }
                Tok::Weekday => {
                    let (e, &k) = Self::name(&self.weekdays, t, p)?;
                    c.weekday = k;
                    p = e;
                }
                Tok::Month => {
                    let (e, k, short) = self.month_at(t, p)?;
                    c.month = k;
                    c.month_short = short;
                    p = e;
                }
                Tok::Day => {
                    let n = t[p..].iter().take_while(|&&x| is_digit(x)).count();
                    if !(1..=2).contains(&n) {
                        return None;
                    }
                    let v = String::from_utf16_lossy(&t[p..p + n]).parse::<u32>().ok()?;
                    if !(1..=31).contains(&v) {
                        return None;
                    }
                    c.day = v;
                    p += n;
                }
                Tok::Year => {
                    let n = t[p..].iter().take_while(|&&x| is_digit(x)).count();
                    let y = &t[p..p + n];
                    if n != 4 || !(y.starts_with(&w("19")) || y.starts_with(&w("20"))) {
                        return None;
                    }
                    c.year = y;
                    p += n;
                }
                Tok::End => {
                    // end of text, or no word right after ("01 Jan - 05 Jan" yes, "3 May players" no)
                    match t.get(p) {
                        None => {}
                        Some(&x) if is_alpha(x) || is_digit(x) => return None,
                        Some(&x) if is_space(x) && t.get(p + 1).is_some_and(|&y| is_alpha(y) || is_digit(y)) => return None,
                        _ => {}
                    }
                }
            }
        }
        Some((p, c))
    }

    fn emit(&self, out: &mut Vec<u16>, he: &[Out], c: &Caps) {
        for o in he {
            match *o {
                Out::Lit(ch) => out.push(ch),
                Out::Weekday { short } => {
                    let (f, s) = &self.he_weekdays[c.weekday];
                    out.extend_from_slice(if short { s } else { f });
                }
                Out::Day => out.extend(c.day.to_string().encode_utf16()),
                Out::Year => out.extend_from_slice(c.year),
                Out::Month { short, prefix } => {
                    if prefix {
                        out.extend_from_slice(&self.prefix);
                    }
                    let (f, s) = &self.he_months[c.month];
                    out.extend_from_slice(if short.unwrap_or(c.month_short) { s } else { f });
                }
            }
        }
    }

    /// `t` with every English date shape in Hebrew, or None when it has none.
    pub fn apply(&self, t: &[u16]) -> Option<Vec<u16>> {
        // every name starts with an upper-case Latin letter
        if self.shapes.is_empty() || !t.iter().any(|&c| (b'A' as u16..=b'Z' as u16).contains(&c)) {
            return None;
        }
        let mut out: Vec<u16> = Vec::new();
        let mut changed = false;
        let mut i = 0;
        while i < t.len() {
            let c = t[i];
            let start_ok = i == 0 || !(is_alpha(t[i - 1]) || is_digit(t[i - 1]));
            if c == b'<' as u16 || (start_ok && (is_digit(c) || (b'A' as u16..=b'Z' as u16).contains(&c))) {
                if let Some((e, caps, he)) = self.shapes.iter().find_map(|(en, he)| self.match_at(en, t, i).map(|(e, c)| (e, c, he))) {
                    if !changed {
                        out.extend_from_slice(&t[..i]);
                        changed = true;
                    }
                    self.emit(&mut out, he, &caps);
                    i = e;
                    continue;
                }
            }
            if changed {
                out.push(c);
            }
            i += 1;
        }
        changed.then_some(out)
    }
}

static mut DATES: Option<Dates> = None;

/// Load `dates=<file>`; returns the number of shapes.
pub unsafe fn load(path: &str) -> usize {
    let Ok(txt) = std::fs::read_to_string(path) else { return 0 };
    let d = Dates::parse(&txt);
    let n = d.len();
    DATES = Some(d);
    n
}

pub fn apply(t: &[u16]) -> Option<Vec<u16>> {
    unsafe { (*core::ptr::addr_of!(DATES)).as_ref()?.apply(t) }
}

#[cfg(test)]
mod tests {
    use super::*;
    const FILE: &str = include_str!("../../../translation/he/dates.txt");

    fn f(s: &str) -> Option<String> {
        let d = Dates::parse(FILE);
        d.apply(&w(s)).map(|v| String::from_utf16_lossy(&v))
    }

    #[test]
    fn file_loads() {
        let d = Dates::parse(FILE);
        assert_eq!(d.he_weekdays.len(), 7);
        assert_eq!(d.he_months.len(), 12);
        assert!(d.len() >= 8);
        assert_eq!(d.prefix, w("ב"));
    }

    #[test]
    fn top_bar() {
        // DateController.UpdateDate: "<b>" + dddd + "</b>,<br>" + "dd MMM yyyy"
        assert_eq!(f("<b>Thursday</b>,<br>01 Jan 2026").as_deref(), Some("<b>יום חמישי</b>,<br>1 בינואר 2026"));
        assert_eq!(f("<b>Friday</b>,<br>02 Jan 2026").as_deref(), Some("<b>יום שישי</b>,<br>2 בינואר 2026"));
        assert_eq!(f("<b>Saturday</b>,<br>31 Dec 2033").as_deref(), Some("<b>שבת</b>,<br>31 בדצמבר 2033"));
        assert_eq!(f("<b>Wednesday</b>,<br>16 Sep 2026").as_deref(), Some("<b>יום רביעי</b>,<br>16 בספטמבר 2026"));
    }

    #[test]
    fn long_dates() {
        // en-US ToLongDateString / "D": the email header
        assert_eq!(f("Thursday, January 1, 2026").as_deref(), Some("יום חמישי, 1 בינואר 2026"));
        assert_eq!(f("Sunday, March 15, 2026").as_deref(), Some("יום ראשון, 15 במרץ 2026"));
        // invariant "dddd, dd MMMM yyyy", en-GB "dddd, d MMMM yyyy"
        assert_eq!(f("Thursday, 01 January 2026").as_deref(), Some("יום חמישי, 1 בינואר 2026"));
        assert_eq!(f("Monday, 5 October 2026").as_deref(), Some("יום שני, 5 באוקטובר 2026"));
        // short names keep the short month form
        assert_eq!(f("Thu, 01 Jan 2026").as_deref(), Some("יום חמישי, 1 בינו׳ 2026"));
        // inside other text, with the rich-text tags around it
        assert_eq!(
            f("<style=Thin 100>Thursday, January 1, 2026</style>").as_deref(),
            Some("<style=Thin 100>יום חמישי, 1 בינואר 2026</style>")
        );
        assert_eq!(f("נשלח: Friday, May 8, 2026\nמאת").as_deref(), Some("נשלח: יום שישי, 8 במאי 2026\nמאת"));
    }

    #[test]
    fn day_month_year() {
        // "MMMM d, yyyy", "d MMMM yyyy", "dd MMM yyyy"
        assert_eq!(f("January 1, 2026").as_deref(), Some("1 בינואר 2026"));
        assert_eq!(f("1 January 2026").as_deref(), Some("1 בינואר 2026"));
        assert_eq!(f("01 Jan 2026").as_deref(), Some("1 בינו׳ 2026"));
        assert_eq!(f("12 Sept 2026").as_deref(), Some("12 בספט׳ 2026"));
        assert_eq!(f("09\u{a0}Feb\u{a0}2027").as_deref(), Some("9 בפבר׳ 2027"));
        // "MMMM yyyy", "MMM yyyy"
        assert_eq!(f("January 2026").as_deref(), Some("ינואר 2026"));
        assert_eq!(f("<b>Aug 2026</b>").as_deref(), Some("<b>אוג׳ 2026</b>"));
        // "d MMMM", "dd MMM" as a whole date
        assert_eq!(f("1 January").as_deref(), Some("1 בינואר"));
        assert_eq!(f("01 Jan - 05 Jan").as_deref(), Some("1 בינו׳ - 5 בינו׳"));
        assert_eq!(f("12 Mar, 13 Mar").as_deref(), Some("12 במרץ, 13 במרץ"));
        // two dates in one text
        assert_eq!(f("From 01 Jan 2026 to 05 Feb 2026").as_deref(), Some("From 1 בינו׳ 2026 to 5 בפבר׳ 2026"));
    }

    #[test]
    fn not_dates() {
        assert_eq!(f(""), None);
        assert_eq!(f("1 email"), None);
        assert_eq!(f("Recent Results"), None);
        assert_eq!(f("<style=Thin 100># </style>12"), None);
        assert_eq!(f("12.05.2026"), None);
        assert_eq!(f("dd.MM.yyyy HH:mm 01.01.2026 10:00"), None);
        // teams and words that are month or weekday names
        assert_eq!(f("May"), None);
        assert_eq!(f("Team May"), None);
        assert_eq!(f("March"), None);
        assert_eq!(f("March Esports 2:1 May Gaming"), None);
        assert_eq!(f("3 May players are ready"), None);
        assert_eq!(f("2 March 5"), None);
        assert_eq!(f("Friday"), None);
        assert_eq!(f("Friday Night Gaming"), None);
        assert_eq!(f("Mayhem 2026"), None);
        assert_eq!(f("Marching 1, 2026"), None);
        assert_eq!(f("Janet 1 2026"), None);
        // numbers that are not a day or a year
        assert_eq!(f("Season 32 Jan"), None);
        assert_eq!(f("January 1, 26"), None);
        assert_eq!(f("Jan 12345"), None);
        assert_eq!(f("Mars 2026"), None);
        // already Hebrew
        assert_eq!(f("<b>יום חמישי</b>,<br>1 בינואר 2026"), None);
    }

    #[test]
    fn then_rtl() {
        // the RTL step after the date pass: number runs are stored reversed (TextMeshPro's right-to-left mode
        // reverses them back on screen), the tags stay paired
        let he = Dates::parse(FILE).apply(&w("<b>Thursday</b>,<br>01 Jan 2026")).unwrap();
        let r = String::from_utf16_lossy(&crate::rtl::tmp_rtl(&he));
        assert_eq!(r, "<b>יום חמישי</b>,<br>1 בינואר 6202");
        assert!(crate::rtl::has_rtl(&he));
    }

    #[test]
    fn hundred_is_not_a_day() {
        // "100 May 2026": 3 digits are not a day; "May 2026" inside it is still a month and year
        assert_eq!(f("100 May 2026").as_deref(), Some("100 מאי 2026"));
        assert_eq!(f("x32 Jan 2026").as_deref(), Some("x32 ינו׳ 2026"));
    }
}
