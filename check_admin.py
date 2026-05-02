import re

with open('static/index.html', encoding='utf-8') as f:
    content = f.read()

# 1. admin-link in HTML
print('=== admin-link occurrences ===')
for m in re.finditer('admin-link', content):
    print(' ', repr(content[m.start()-40:m.start()+80]))

# 2. switchView admin guard
print('\n=== switchView admin guard ===')
idx = content.find("view === 'admin'")
if idx >= 0:
    print(repr(content[idx-20:idx+120]))
else:
    print('NOT FOUND')

# 3. Admin nav link onclick
print('\n=== Admin nav link ===')
idx2 = content.find("switchView('admin')")
while idx2 >= 0:
    print(repr(content[idx2-60:idx2+60]))
    idx2 = content.find("switchView('admin')", idx2+1)

# 4. Admin tabs
print('\n=== Admin tabs ===')
print('switchAdminTab:', 'switchAdminTab' in content)
print('admin-tab-news:', 'admin-tab-news' in content)
print('admin-tab-users:', 'admin-tab-users' in content)
print('loadAdminData:', 'loadAdminData' in content)

# 5. Check admin-link style in init
print('\n=== admin-link show in init ===')
idx3 = content.find("admin-link")
for m in re.finditer("admin-link", content):
    ctx = content[m.start()-20:m.start()+80]
    if 'display' in ctx or 'block' in ctx or 'none' in ctx:
        print(repr(ctx))
