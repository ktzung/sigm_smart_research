"""Check UI JS for common issues."""
with open('static/index.html', encoding='utf-8') as f:
    content = f.read()

rc_pos = content.find('function renderStageCard')
lp_pos = content.find('async function loadPipelineTab')
sl_pos = content.find('const STAGE_LABELS')

print(f'STAGE_LABELS global   : char {sl_pos}')
print(f'renderStageCard       : char {rc_pos}')
print(f'loadPipelineTab       : char {lp_pos}')
print(f'Order OK              : {sl_pos < rc_pos < lp_pos}')

# Check backticks in renderStageCard body
rc_body = content[rc_pos:rc_pos+2500]
bt_count = rc_body.count('`')
print(f'Backticks in renderStageCard: {bt_count} (should be 0)')

# Check loadPipelineTab uses renderStageCard
uses_render = 'renderStageCard' in content[lp_pos:lp_pos+3000]
print(f'loadPipelineTab calls renderStageCard: {uses_render}')

# Check no stageLabels reference (old variable)
old_ref = 'stageLabels[' in content[lp_pos:lp_pos+3000]
print(f'Old stageLabels reference: {old_ref} (should be False)')

print('\nAll checks passed!' if (sl_pos < rc_pos < lp_pos and bt_count == 0 and uses_render and not old_ref) else '\nISSUES FOUND')
