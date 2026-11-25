"""Build replacement fonts (Latin + Hebrew, SIL OFL) for every Latin font slot Dispatch uses.

    python tools/build_fonts.py fonts/src <out folder>

A cooked .ufont is the raw TTF, so each slot simply gets our TTF: Noto Sans + Noto Sans Hebrew,
instanced at the slot's weight (from its file name) and width (narrow for the condensed families),
then merged. Italic slots get the upright font (Hebrew has no italics).
"""
import os, sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.merge import Merger

S = 'Dispatch/Content/Shared/'
SLOTS = [S + 'Shifts/Art/Fonts/' + p for p in [
    'Aktiv_Grotesk.ufont', 'Input/Input-Bold__InputMono-Bold_.ufont', 'Roboto_Mono/RobotoMono-Bold.ufont',
    'Roboto_Regular/Roboto-Bold.ufont', 'Roboto_Regular/Roboto-BoldItalic.ufont', 'Roboto_Regular/Roboto-Medium.ufont',
    'Roboto_Regular/Roboto-Regular.ufont', 'SourceCodePro/SourceCodePro-Light.ufont',
    'schaboxcondensed/SCHABO-XCondensed.ufont']]
SLOTS += [S + 'Shifts/Art/UI/Fonts/Tomorrow/Tomorrow-' + w + '.ufont' for w in ['Black', 'Bold', 'Medium', 'Regular', 'SemiBold']]
SLOTS += [S + 'UI/Fonts/Barlow/Barlow-Black.ufont']
SLOTS += [S + 'UI/Fonts/Montserrat/static/Montserrat-' + w + '.ufont' for w in [
    'Black', 'BlackItalic', 'Bold', 'BoldItalic', 'ExtraBold', 'ExtraBoldItalic', 'ExtraLight', 'ExtraLightItalic',
    'Italic', 'Light', 'LightItalic', 'Medium', 'MediumItalic', 'Regular', 'SemiBold', 'SemiBoldItalic', 'Thin', 'ThinItalic']]
SLOTS += [S + 'UI/Fonts/NotoSans/NotoSans-' + w + '.ufont' for w in [
    'Black', 'Bold', 'ExtraBold', 'ExtraLight', 'Light', 'Medium', 'Regular', 'SemiBold', 'Thin']]
SLOTS += [S + 'UI/Fonts/Orbitron/Orbitron-' + w + '.ufont' for w in ['Black', 'Bold', 'ExtraBold', 'Medium', 'Regular', 'SemiBold']]
SLOTS += [S + 'UI/Fonts/Rajdhani/Rajdhani-' + w + '.ufont' for w in ['Bold', 'Light', 'Medium', 'Regular', 'SemiBold']]
SLOTS += ['Engine/Content/EngineFonts/Faces/Roboto' + w + '.ufont' for w in ['Bold', 'BoldItalic', 'Italic', 'Light', 'Regular']]

WEIGHTS = [('ExtraLight', 200), ('ExtraBold', 800), ('SemiBold', 600), ('Thin', 100), ('Light', 300),
           ('Medium', 500), ('Bold', 700), ('Black', 900)]


def style(slot):
    name = os.path.basename(slot)
    wght = next((v for k, v in WEIGHTS if k in name), 400)
    if 'SCHABO' in name:
        return 800, 62.5
    if 'Rajdhani' in name or 'Barlow' in name:
        return wght, 75
    return wght, 100


def instance(path, wght, wdth, out):
    f = TTFont(path)
    axes = {a.axisTag: a.defaultValue for a in f['fvar'].axes}
    axes['wght'] = wght
    if 'wdth' in axes:
        axes['wdth'] = wdth
    inst = instancer.instantiateVariableFont(f, axes)
    for tag in ('STAT', 'MVAR', 'HVAR', 'meta', 'DSIG'):
        if tag in inst:
            del inst[tag]
    inst.save(out)
    return out


def build(src, work, wght, wdth):
    out = os.path.join(work, f'noto-{wght}-{wdth}.ttf')
    if os.path.exists(out):
        return out
    a = instance(os.path.join(src, 'notosans__NotoSans.ttf'), wght, wdth, os.path.join(work, 'a.ttf'))
    h = instance(os.path.join(src, 'notosanshebrew__NotoSansHebrew.ttf'), wght, wdth, os.path.join(work, 'h.ttf'))
    m = Merger().merge([a, h])
    for rec in m['name'].names:
        if rec.nameID in (1, 3, 4, 16):
            rec.string = f'Tirgumim Noto {wght} {wdth}'
        elif rec.nameID == 6:
            rec.string = f'TirgumimNoto-{wght}-{int(wdth)}'
    m.save(out)
    return out


def main(src, out):
    work = os.path.join(out, '_work')
    os.makedirs(work, exist_ok=True)
    for slot in SLOTS:
        f = build(src, work, *style(slot))
        dst = os.path.join(out, slot)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(f, 'rb') as a, open(dst, 'wb') as b:
            b.write(a.read())
    print(len(SLOTS), 'font slots')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
