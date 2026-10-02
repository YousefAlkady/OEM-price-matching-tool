import os

path = r'C:\Users\A\Desktop\UniLink\src\components\feed-v2\PostImageCarousel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """ <div className={cn("mt-3 rounded-xl border border-border relative bg-muted/50 overflow-hidden flex justify-center bg-black/5", className)}>
 {/* Absolute-positioned slides — ensures images truly fill the aspect-ratio box and object-center crops from the middle */}
 <div className="w-full flex justify-center items-center">
 {images.map((url, i) => (
  <img
  key={i}
  src={i === current ? (optimizeImage(url, 800, 75) ?? url) : undefined}
  alt={`Post image ${i + 1}`}
  loading="lazy"
  decoding="async"
  style={{ display: i === current ? "block" : "none" }}
  className={cn("max-h-[600px] w-auto max-w-full object-contain cursor-pointer", imgClassName)}
  onClick={(e) => {
  e.stopPropagation();
  openFullscreen(i);
  }}
  />
  ))}
 </div>"""

new_block = """ <div className={cn("mt-3 rounded-xl border border-border relative bg-black overflow-hidden aspect-[4/5]", className)}>
 <div className="absolute inset-0">
 {images.map((url, i) => (
  <div
  key={i}
  className="absolute inset-0 flex items-center justify-center"
  style={{ display: i === current ? "flex" : "none" }}
  >
  <img
  src={i === current ? (optimizeImage(url, 800, 75) ?? url) : undefined}
  alt={`Post image ${i + 1}`}
  loading="lazy"
  decoding="async"
  className={cn("w-full h-full object-contain cursor-pointer", imgClassName)}
  onClick={(e) => {
  e.stopPropagation();
  openFullscreen(i);
  }}
  />
  </div>
  ))}
 </div>"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replaced successfully")
else:
    print("Block not found")
