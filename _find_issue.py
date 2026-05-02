content = open('static/index.html', encoding='utf-8').read()
import re

# Find all occurrences of loadRoutingTable being called or defined
for m in re.finditer(r'loadRoutingTable', content):
    ctx = content[m.start()-30:m.start()+60]
    print(f'At {m.start()}: {repr(ctx)}')

print()

# Find the exact browser line 4956 - browser counts differently
# Browser line = HTML line in the file
lines = content.split('\n')
print(f'Total HTML lines: {len(lines)}')
print(f'Line 4956: {repr(lines[4955][:120])}')
print(f'Line 4955: {repr(lines[4954][:120])}')
print(f'Line 4957: {repr(lines[4956][:120])}')

# Check for stray } at line 4956
print()
print('Lines 4950-4960:')
for i in range(4949, 4960):
    print(f'  {i+1}: {repr(lines[i][:120])}')
