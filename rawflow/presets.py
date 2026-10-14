"""Shared preset definitions for RAW profiles and responsive draft previews."""
PRESETS = {
    'natural': dict(contrast=0, saturation=0, shadows=0, highlights=0),
    'punchy': dict(contrast=12, saturation=10, shadows=35, highlights=25),
    'saturated': dict(contrast=8, saturation=28, shadows=25, highlights=25),
    'black-and-white': dict(contrast=18, saturation=0, shadows=30, highlights=30, monochrome=True),
    'filmic': dict(contrast=-6, saturation=-12, shadows=20, highlights=35, tone='filmic'),
    'arty': dict(contrast=24, saturation=20, shadows=25, highlights=30, tone='arty'),
}
LABELS = {'Natural': 'natural', 'Punchy': 'punchy', 'Saturated': 'saturated',
          'Black and white': 'black-and-white', 'Filmic': 'filmic', 'Arty': 'arty'}


STRENGTHS = {'low': 1., 'medium': 1.25, 'high': 1.5}


def preset_settings(look, strength='low'):
    factor = STRENGTHS[strength]
    settings = dict(PRESETS[look])
    for key in ('contrast', 'saturation', 'shadows', 'highlights'):
        settings[key] = round(settings[key] * factor)
    if settings.get('tone'):
        settings['tone_strength'] = factor
    return settings


def draft_preview(image, look, scene='preserve', wb='camera', strength='low'):
    """Approximate the look on a camera JPEG; never used to generate exports."""
    import numpy as np
    from PIL import Image
    p = preset_settings(look, strength)
    factor = STRENGTHS[strength]
    small = image.copy()
    small.thumbnail((1000, 800))
    rgb = np.asarray(small, dtype=np.float32) / 255
    if scene == 'normal':
        rgb *= min(1.3, max(.85, .48 / max(float(np.median(rgb)), .05)))
    if wb == 'neutral-search':
        mask = (rgb.max(2)-rgb.min(2) < .08) & (rgb.mean(2) > .2) & (rgb.mean(2) < .8)
        if mask.mean() >= .01:
            means = rgb[mask].mean(0)
            rgb *= np.clip(means.mean() / np.maximum(means, .01), .85, 1.15)
    rgb += (p['shadows']/350) * (1-rgb)**3
    rgb = (rgb-.5)*(1+p['contrast']/100)+.5
    lum = rgb @ np.array([.2126,.7152,.0722], dtype=np.float32)
    rgb = lum[:,:,None] + (rgb-lum[:,:,None])*(1+p['saturation']/100)
    if p.get('monochrome'):
        rgb = np.repeat(lum[:,:,None],3,axis=2)
    if p.get('tone') == 'filmic':
        rgb = .035*factor + np.clip(rgb,0,1)*(1-.07*factor)
    if p.get('tone') == 'arty':
        rgb[:,:,0] += .035*factor*rgb[:,:,0]
        rgb[:,:,2] += .055*factor*(1-rgb[:,:,2])
    return Image.fromarray((np.clip(rgb,0,1)*255+.5).astype('uint8'))
