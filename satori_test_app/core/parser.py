import re

class SatoriBlock:
    def __init__(self, type_mark, name, condition=None):
        self.type_mark = type_mark # '＊' or '＠'
        self.name = name
        self.condition = condition
        self.lines = []

    def __repr__(self):
        return f"SatoriBlock({self.type_mark}, {self.name}, cond={self.condition}, lines={len(self.lines)})"

def parse_dict_file(filepath):
    blocks = []
    current_block = None

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.rstrip('\n\r')
            if not line:
                if current_block and current_block.type_mark == '＠':
                    # Word groups usually don't care about empty lines at the end,
                    # but let's keep them if they are in the middle.
                    pass
                elif current_block:
                    current_block.lines.append(line)
                continue

            # Check for block start
            if line.startswith('＊') or line.startswith('＠'):
                mark = line[0]
                content = line[1:]
                name = content
                condition = None

                # Check for 【タブ】 (Tab) or actual Tab character
                if '\t' in content:
                    name, condition = content.split('\t', 1)
                elif '【タブ】' in content:
                    name, condition = content.split('【タブ】', 1)

                current_block = SatoriBlock(mark, name, condition)
                blocks.append(current_block)
            elif line.startswith('＃'):
                # Comment line outside of blocks is ignored.
                if current_block:
                    current_block.lines.append(line)
            else:
                if current_block:
                    if current_block.type_mark == '＠' and current_block.lines:
                        # For word groups, if previous line has unbalanced parens,
                        # or ends with φ, join with current line instead of adding as new entry.
                        prev_line = current_block.lines[-1]
                        if prev_line.count('（') > prev_line.count('）') or prev_line.endswith('φ'):
                             current_block.lines[-1] = prev_line + "\n" + line
                             continue
                    current_block.lines.append(line)
                else:
                    pass
    return blocks
