from PIL import Image
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
base = r'C:\Users\Admin\Downloads\AI Web\buddymath\buddymath\FE\images\v2'
out = r'C:\Users\Admin\Downloads\AI Web\buddymath\buddymath\design\refs\_crops'
for name in ('parent-empty-art.png','parent-tip-art.png','parent-banner-art.png'):
    im = Image.open(base + '\\' + name).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 0, 255, 255))
    bg.alpha_composite(im)
    bg.convert('RGB').resize((im.width*2, im.height*2), Image.LANCZOS).save(out + '\\alpha_' + name)
    print(name, im.size)
