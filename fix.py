import os

path = r'C:\Users\A\Desktop\UniLink\src\components\feed-v2\PostImageCarousel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Change the main container
content = content.replace(
    '<div className={cn("mt-3 rounded-xl border border-border aspect-video relative bg-muted/50 overflow-hidden", className)}>',
    '<div className={cn("mt-3 rounded-xl border border-border relative bg-muted/50 overflow-hidden flex justify-center bg-black/5", className)}>'
)

# 2. Change the img wrapper and img
old_img_block = ''' <div className="absolute inset-0">
 {images.map((url, i) => (
  <div
  key={i}
  className="absolute inset-0"
  style={{ display: i === current ? "block" : "none" }}
  >
  <img
  src={i === current ? (optimizeImage(url, 800, 75) ?? url) : undefined}
  alt={`Post image ${i + 1}`}
  loading="lazy"
  decoding="async"
  className={cn("w-full h-full object-cover object-center cursor-pointer", imgClassName)}
  onClick={(e) => {
  e.stopPropagation();
  openFullscreen(i);
  }}
  />
  </div>
  ))}
 </div>'''

new_img_block = ''' <div className="w-full flex justify-center items-center">
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
 </div>'''

content = content.replace(old_img_block, new_img_block)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Replaced successfully")
