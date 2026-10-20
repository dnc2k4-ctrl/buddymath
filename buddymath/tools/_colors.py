from PIL import Image
im = Image.open(r'C:\Users\Admin\Downloads\AI Web\buddymath\buddymath\design\refs\03-parent.png').convert('RGB')
for x in (30, 20, 45, 50):
    print(f"=== x={x} (y 455..700, step1, print all)")
    prev=None
    for y in range(455, 700):
        c = im.getpixel((x,y))
        d = 0 if prev is None else sum(abs(a-b) for a,b in zip(c,prev))
        if x<45 or d>6:
            print(y, '#%02X%02X%02X' % c, d)
        prev = c
