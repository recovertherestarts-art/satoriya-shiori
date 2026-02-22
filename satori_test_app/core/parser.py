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
                # Inside blocks, it might be handled by the interpreter.
                if current_block:
                    current_block.lines.append(line)
            else:
                if current_block:
                    current_block.lines.append(line)
                else:
                    # Content before any block is ignored or treated as comments
                    pass
    return blocks
