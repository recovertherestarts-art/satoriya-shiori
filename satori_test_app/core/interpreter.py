import random
import re
import math

class SatoriInterpreter:
    def __init__(self):
        self.variables = {}
        self.sentences = {}  # Name -> list of SatoriBlock
        self.word_groups = {}  # Name -> list of SatoriBlock
        self.norm_sentences = {}
        self.norm_word_groups = {}
        self.random_talks = [] # list of SatoriBlock (unnamed)
        self.current_scope = 1 # Start at 1 so first ':' toggles to 0 (\0)
        self.output_buffer = []
        self.is_jumping = False
        self.jump_target = None

        # System variables default
        self.variables['B0'] = '\x00'
        self.variables['B1'] = '\x01'
        self.variables['B2'] = '\x02'
        self.variables['B3'] = '\x03'
        self.variables['バイト値、１'] = '\x01'
        self.variables['バイト値、２'] = '\x02'
        self.variables['バイト値、３'] = '\x03'

    def load_blocks(self, blocks):
        self.norm_sentences = {}
        self.norm_word_groups = {}
        for block in blocks:
            if block.type_mark == '＊':
                if not block.name:
                    self.random_talks.append(block)
                else:
                    if block.name not in self.sentences:
                        self.sentences[block.name] = []
                    self.sentences[block.name].append(block)
                    self.norm_sentences[self.normalize_name(block.name)] = block.name
            elif block.type_mark == '＠':
                if block.name not in self.word_groups:
                    self.word_groups[block.name] = []
                self.word_groups[block.name].append(block)
                self.norm_word_groups[self.normalize_name(block.name)] = block.name

    def eval_condition(self, condition):
        if not condition:
            return True

        expanded = self.expand_string(condition).strip().replace('\n', '').replace('\r', '')

        # Satori operators: ==, !=, >=, <=, >, <, =, etc.
        # Also full-width versions.
        ops = [
            ('＝＝', '=='), ('==', '=='),
            ('！＝', '!='), ('!=', '!='),
            ('＞＝', '>='), ('>=', '>='),
            ('＜＝', '<='), ('<=', '<='),
            ('＞', '>'), ('>', '>'),
            ('＜', '<'), ('<', '<'),
            ('＝', '=='), ('=', '==')
        ]

        # Find the operator
        found_op = None
        left, right = expanded, ""

        for s_op, p_op in ops:
            if s_op in expanded:
                found_op = p_op
                left, right = expanded.split(s_op, 1)
                break

        if found_op:
            left = left.strip()
            right = right.strip()

            # Numeric comparison if both are digits
            try:
                l_num = float(self.normalize_name(left))
                r_num = float(self.normalize_name(right))
                if found_op == '==': return l_num == r_num
                if found_op == '!=': return l_num != r_num
                if found_op == '>=': return l_num >= r_num
                if found_op == '<=': return l_num <= r_num
                if found_op == '>': return l_num > r_num
                if found_op == '<': return l_num < r_num
            except ValueError:
                # String comparison
                l_str = self.normalize_name(left)
                r_str = self.normalize_name(right)
                if found_op == '==': return l_str == r_str
                if found_op == '!=': return l_str != r_str
                # For others, string comparison might be weird but let's do it
                if found_op == '>=': return l_str >= r_str
                if found_op == '<=': return l_str <= r_str
                if found_op == '>': return l_str > r_str
                if found_op == '<': return l_str < r_str
        else:
            # No operator, check if non-zero/non-empty
            val = expanded.strip()
            if not val: return False
            try:
                return float(self.normalize_name(val)) != 0
            except ValueError:
                return True # Non-empty string is True

    def handle_escape(self, s):
        if s is None: return ""
        res = []
        i = 0
        while i < len(s):
            if s[i] == 'φ':
                if i + 1 < len(s):
                    if s[i+1] == '\n':
                        i += 2
                        continue
                    if s[i+1] == '\r':
                        if i + 2 < len(s) and s[i+2] == '\n': i += 3
                        else: i += 2
                        continue
                    # Mark as escaped
                    res.append("\ufffd" + s[i+1])
                    i += 2
                else:
                    i += 1
            else:
                res.append(s[i])
                i += 1
        return "".join(res)

    def expand_string(self, s):
        if s is None: return ""
        s = self.handle_escape(s)

        # Process from left to right to avoid infinite loops on unresolvable identifiers
        pos = 0
        while True:
            start = -1
            for j in range(pos, len(s)):
                if s[j] == '（':
                    if j > 0 and s[j-1] == "\ufffd":
                        continue
                    start = j
                    break

            if start == -1: break

            depth = 1
            end = -1
            for i in range(start + 1, len(s)):
                if s[i] == '（': depth += 1
                elif s[i] == '）': depth -= 1
                if depth == 0:
                    end = i
                    break

            if end == -1:
                pos = start + 1
                continue

            inner = s[start+1:end]
            # Peek at function name for special expansion
            # Must use same smart split logic to avoid splitting on nested delimiters
            args = []
            current = []
            d_depth = 0
            for char in inner:
                if char == '（': d_depth += 1
                elif char == '）': d_depth -= 1
                elif d_depth == 0 and char in [',', '、']:
                    args.append("".join(current))
                    current = []
                    continue # only use the first delimiter found for splitting function name?
                    # Satori is complex here. Let's just split all.
                current.append(char)
            args.append("".join(current))

            func_name = args[0]

            if func_name in ['when', 'whenlist', 'iflist', 'switch', 'nswitch', 'times', 'for', 'while']:
                # Pass the raw arguments (inner after func name)
                # We need to find where the first arg starts
                first_delim_pos = -1
                d_depth = 0
                for idx, char in enumerate(inner):
                    if char == '（': d_depth += 1
                    elif char == '）': d_depth -= 1
                    elif d_depth == 0 and char in [',', '、']:
                        first_delim_pos = idx
                        break

                raw_args = []
                if first_delim_pos != -1:
                    # Split the rest by the SAME delimiter
                    delim = inner[first_delim_pos]
                    rest = inner[first_delim_pos+1:]
                    # Smart split rest by delim
                    curr = []
                    dd = 0
                    for c in rest:
                        if c == '（': dd += 1
                        elif c == '）': dd -= 1
                        elif dd == 0 and c == delim:
                            raw_args.append("".join(curr))
                            curr = []
                            continue
                        curr.append(c)
                    raw_args.append("".join(curr))

                expanded_content = self.call_function(func_name, raw_args)
            else:
                expanded_inner = self.expand_string(inner)
                expanded_content = self.process_parenthesis(expanded_inner)

            # Re-handle escape in the newly expanded content
            expanded_content = self.handle_escape(expanded_content)

            # If expansion didn't change anything, move past it to avoid infinite loop
            if expanded_content == "（" + inner + "）":
                pos = start + len(expanded_content)
            else:
                # Keep same pos to re-check the new content
                pass

            s = s[:start] + expanded_content + s[end+1:]

        return s.replace("\ufffd", "")

    def process_parenthesis(self, content):
        # Check for function call with potential delimiters
        # Delimiters can be \x01, \x02, \x03, , 、
        # We must only split by delimiters at the top level of nesting
        delimiters = ['\x01', '\x02', '\x03', ',', '、']

        chosen_delim = None
        for d in delimiters:
            depth = 0
            for char in content:
                if char == '（': depth += 1
                elif char == '）': depth -= 1
                elif depth == 0 and char == d:
                    chosen_delim = d
                    break
            if chosen_delim: break

        if chosen_delim:
            args = []
            current = []
            depth = 0
            for char in content:
                if char == '（': depth += 1
                elif char == '）': depth -= 1
                elif depth == 0 and char == chosen_delim:
                    args.append("".join(current))
                    current = []
                    continue
                current.append(char)
            args.append("".join(current))

            func_name = args[0]
            return self.call_function(func_name, args[1:])
        else:
            # Variable, Word group, or Sentence call
            return self.resolve_identifier(content)

    def resolve_identifier(self, name):
        if not name: return ""
        # 0. Special identifiers
        if name.startswith('バイト値'):
            # (バイト値、１)
            parts = re.split(r'[,、]', name)
            if len(parts) > 1:
                try:
                    num = int(parts[1].translate(str.maketrans('０１２３４５６７８９', '0123456789')))
                    return chr(num)
                except:
                    pass

        if name.startswith('乱数'):
            # (乱数１～１０)
            m = re.search(r'([0-9０-９]+)～([0-9０-９]+)', name)
            if m:
                try:
                    low = int(m.group(1).translate(str.maketrans('０１２３４５６７８９', '0123456789')))
                    high = int(m.group(2).translate(str.maketrans('０１２３４５６７８９', '0123456789')))
                    return str(random.randint(low, high))
                except:
                    pass

        if name == 'Ｓの数':
            count = 0
            while f'Ｓ{count}' in self.variables:
                count += 1
            return str(count)

        if name == 'Ｒの数':
            count = 0
            while f'Ｒ{count}' in self.variables:
                count += 1
            return str(count)

        # 1. Variable
        norm_name = self.normalize_name(name)
        # Check for exact match first
        if name in self.variables:
            return str(self.variables[name])
        # Check for normalized match
        for k, v in self.variables.items():
            if self.normalize_name(k) == norm_name:
                return str(v)

        # 2. Word group @
        norm_name = self.normalize_name(name)
        actual_wg = self.norm_word_groups.get(norm_name)

        if actual_wg:
            # Pick a random line from eligible blocks
            eligible_blocks = [b for b in self.word_groups[actual_wg] if self.eval_condition(b.condition)]
            if eligible_blocks:
                block = random.choice(eligible_blocks)
                if block.lines:
                    # Execute as a block to handle multiple lines joined by φ
                    return self.execute_block(block)
            return ""

        # 3. Sentence *
        # Use execute_block_name which already normalizes
        norm_name = self.normalize_name(name)
        if norm_name in self.norm_sentences:
            return self.execute_block_name(name)

        # 4. Surface number?
        if name.isdigit():
            return f"\\s[{name}]"

        # Not found
        return f"（{name}）"

    def call_function(self, name, args):
        # Implement built-in functions
        if name == 'if' or name == 'when' or name == 'unless':
            cond = args[0]
            is_true = self.eval_condition(cond)
            if name == 'unless':
                is_true = not is_true

            if is_true:
                return self.expand_string(args[1])
            elif len(args) > 2:
                return self.expand_string(args[2])
            return ""

        if name == 'switch':
            left = self.expand_string(args[0])
            for i in range(1, len(args) - 1, 2):
                right = self.expand_string(args[i])
                if left == right:
                    return self.expand_string(args[i+1])
            # Default case
            if len(args) % 2 == 0:
                return self.expand_string(args[-1])
            return ""

        if name == 'iflist' or name == 'whenlist':
            left = self.expand_string(args[0])
            for i in range(1, len(args) - 1, 2):
                right = args[i]
                res = args[i+1]
                if self.eval_condition(left + right):
                    return self.expand_string(res)
            # Default case
            if len(args) % 2 == 0:
                return self.expand_string(args[-1])
            return ""

        if name == 'nswitch':
            try:
                val = int(self.expand_string(args[0]).translate(str.maketrans('０１２３４５６７８９', '0123456789')))
                if 1 <= val < len(args):
                    return self.expand_string(args[val])
            except:
                pass
            return ""

        if name == 'calc' or name == 'calc_float':
            raw_expr = self.expand_string(args[0])
            expr = raw_expr.translate(str.maketrans('０１２３４５６７８９＋－×÷＝', '0123456789+-*/='))
            expr = expr.replace('÷', '/')
            expr = expr.replace('×', '*')
            try:
                # Basic sanitization for eval
                if not re.match(r'^[0-9. +\-*/()%]*$', expr.strip()):
                    return raw_expr # Return raw if not a formula
                result = eval(expr, {"__builtins__": None}, {})
                if name == 'calc':
                    return str(int(result))
                return str(result)
            except:
                return raw_expr # Return raw on failure

        if name == 'loop':
            target = args[0]
            count_str = self.expand_string(args[1])
            try:
                count = int(count_str.translate(str.maketrans('０１２３４５６７８９', '0123456789')))
            except:
                count = 0

            results = []
            orig_counter = self.variables.get(f"{target}カウンタ")
            for i in range(count):
                self.variables[f"{target}カウンタ"] = str(i)
                results.append(self.resolve_identifier(target))

            if orig_counter is not None:
                self.variables[f"{target}カウンタ"] = orig_counter
            else:
                self.variables.pop(f"{target}カウンタ", None)

            return "".join(results)

        if name == 'for':
            # (for, start, end, step, body)
            try:
                start = int(self.call_function('calc', [args[0]]))
                end = int(self.call_function('calc', [args[1]]))
                step = 1
                body_idx = 2
                if len(args) > 3:
                    step = int(self.call_function('calc', [args[2]]))
                    body_idx = 3
            except:
                return ""

            body = args[body_idx]
            results = []
            orig_c0 = self.variables.get('Ｃ０')

            # Python's range doesn't include the end, but Satori's for usually does?
            # Satori for: from start to end inclusive.
            r = range(start, end + 1, step) if step > 0 else range(start, end - 1, step)
            for i in r:
                self.variables['Ｃ０'] = str(i)
                results.append(self.expand_string(body))

            self.variables['Ｃ０'] = orig_c0
            return "".join(results)

        if name == 'times':
            try:
                count = int(self.call_function('calc', [args[0]]))
            except:
                count = 0
            body = args[1]
            results = []
            orig_c0 = self.variables.get('Ｃ０')
            for i in range(count):
                self.variables['Ｃ０'] = str(i)
                results.append(self.expand_string(body))
            self.variables['Ｃ０'] = orig_c0
            return "".join(results)

        if name == 'set':
            var_name = args[0]
            val = self.expand_string(args[1])
            self.variables[var_name] = val
            return ""

        if name == 'nop':
            if args:
                self.expand_string(args[0])
            return ""

        if name == 'at':
            target = self.expand_string(args[0])
            try:
                pos = int(self.call_function('calc', [args[1]]))
                if 0 <= pos < len(target):
                    return target[pos]
            except:
                pass
            return ""

        if name == 'length':
            return str(len(self.expand_string(args[0])))

        if name == 'count':
            target = self.expand_string(args[0])
            sub = self.expand_string(args[1])
            if not sub: return "0"
            return str(target.count(sub))

        if name == 'replace' or name == 'replace_first':
            target = self.expand_string(args[0])
            old = self.expand_string(args[1])
            new = self.expand_string(args[2])
            if name == 'replace':
                return target.replace(old, new)
            else:
                return target.replace(old, new, 1)

        if name == 'substr':
            target = self.expand_string(args[0])
            try:
                start = int(self.call_function('calc', [args[1]]))
                length = len(target)
                if len(args) > 2:
                    count = int(self.call_function('calc', [args[2]]))
                    if count >= 0:
                        return target[start:start+count]
                    else:
                        # Negative length in Satori means from start backwards?
                        # "5, -3" from "あいうえおかきくけこ" (pos 5 is 'か') -> "うえお"
                        return target[start+count:start]
                return target[start:]
            except:
                pass
            return ""

        if name == 'call':
            target = args[0]
            # Save old args
            old_args = {}
            for i in range(10): # Usually up to 10
                key = f'Ａ{i}'
                if key in self.variables:
                    old_args[key] = self.variables[key]

            # Set new args
            for i, arg in enumerate(args[1:]):
                self.variables[f'Ａ{i}'] = self.expand_string(arg)

            result = self.resolve_identifier(target)

            # Restore old args
            for i in range(10):
                key = f'Ａ{i}'
                if key in old_args:
                    self.variables[key] = old_args[key]
                else:
                    self.variables.pop(key, None)
            return result

        if name == 'split':
            # (split, string, sep, max, empty)
            target = self.expand_string(args[0])
            sep = args[1] if len(args) > 1 else ""

            if not sep:
                parts = list(target)
            else:
                # Satori split: if sep is multiple chars, it splits by ANY of them?
                # Actually Wiki says: split uses each char in sep as a delimiter.
                # split_string uses the whole sep as a delimiter.
                regex_sep = '[' + re.escape(sep) + ']'
                parts = re.split(regex_sep, target)

            # Handle empty elements
            empty = args[4] if len(args) > 4 else "0"
            if empty == "0":
                parts = [p for p in parts if p]

            for i, p in enumerate(parts):
                self.variables[f'Ｓ{i}'] = p

            return str(len(parts))

        # SAORI call simulation
        # In this interpreter, we treat unknown functions as potential SAORI calls if they are not in our built-ins.
        # But for testing, we'll look at a "saori_mocks" map.
        if hasattr(self, 'saori_mocks') and name in self.saori_mocks:
            mock = self.saori_mocks[name]
            if callable(mock):
                return mock(*args)
            return str(mock)

        return f"（{name},{','.join(args)}）"

    def normalize_name(self, name):
        if not name: return ""
        # Convert full-width numbers and alphabets to half-width for matching
        # Also lowercase for case-insensitivity
        zen = '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
        han = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        return name.translate(str.maketrans(zen, han)).lower()

    def execute_block(self, block):
        self.is_jumping = False
        block_output = []

        for line in block.lines:
            if self.is_jumping:
                break

            if not line:
                block_output.append("\n")
                continue

            # Remove inline comments
            if '＃' in line:
                line = line.split('＃', 1)[0]
                if not line:
                    continue

            if line.startswith('＃'):
                continue

            if line.startswith('：'):
                # Scope change
                self.current_scope = 1 - self.current_scope
                block_output.append(f"\\{self.current_scope}")
                content = line[1:]
                block_output.append(self.expand_string(content))
            elif line.startswith('＄'):
                # Variable assignment
                content = line[1:]
                if '【タブ】' in content:
                    var_name, val = content.split('【タブ】', 1)
                    expanded_var = self.expand_string(var_name)
                    self.variables[expanded_var] = self.expand_string(val)
                elif '\t' in content:
                    var_name, val = content.split('\t', 1)
                    expanded_var = self.expand_string(var_name)
                    self.variables[expanded_var] = self.expand_string(val)
                elif '＝' in content:
                    var_name, val = content.split('＝', 1)
                    # Satori = evaluates the expression
                    expanded_var = self.expand_string(var_name)
                    self.variables[expanded_var] = self.call_function('calc', [val])
                elif '=' in content:
                    var_name, val = content.split('=', 1)
                    expanded_var = self.expand_string(var_name)
                    self.variables[expanded_var] = self.call_function('calc', [val])
            elif line.startswith('＞') or line.startswith('≫'):
                # Jump
                content = line[1:]
                target = content
                condition = None
                if '【タブ】' in content:
                    target, condition = content.split('【タブ】', 1)
                elif '\t' in content:
                    target, condition = content.split('\t', 1)

                target = self.expand_string(target)
                if self.eval_condition(condition):
                    # Only jump if target exists
                    norm_target = self.normalize_name(target)
                    actual_target = self.norm_sentences.get(norm_target)

                    if actual_target:
                        self.is_jumping = True
                        self.jump_target = actual_target
                        break
                    # If not exists, continue to next line
            elif line.startswith('≧'):
                # Tag jump
                content = line[1:]
                prefix = ""
                tag = ""
                if '「' in content:
                    prefix, tag = content.split('「', 1)
                else:
                    prefix = content

                tag = self.expand_string(tag).strip()
                # Search sentences
                candidates = []
                norm_prefix = self.normalize_name(prefix)
                for s_name in self.sentences:
                    norm_s_name = self.normalize_name(s_name)
                    if norm_s_name.startswith(norm_prefix + '「'):
                        tags_part = s_name.split('「', 1)[1]
                        # Use same normalization for tags too
                        tags = [self.normalize_name(t) for t in re.split(r'[ 　\t]+', tags_part.strip())]
                        if self.normalize_name(tag) in tags:
                            candidates.append(s_name)

                if candidates:
                    # Satori picks one
                    self.is_jumping = True
                    self.jump_target = random.choice(candidates)
                    break
            else:
                # Normal talk line
                block_output.append(self.expand_string(line))

        final_output = "".join(block_output)

        if self.is_jumping:
            # Execute the jump target
            return final_output + self.execute_block_name(self.jump_target)

        return final_output

    def execute_block_name(self, name):
        norm_name = self.normalize_name(name)
        actual_name = self.norm_sentences.get(norm_name)

        if not actual_name:
            return ""

        eligible_blocks = [b for b in self.sentences[actual_name] if self.eval_condition(b.condition)]
        if not eligible_blocks:
            return ""

        # Satori chooses one block (can be random or priority based, here we just pick one)
        block = random.choice(eligible_blocks)
        return self.execute_block(block)

    def run_event(self, event_name, references=[]):
        # Set References
        for i, ref in enumerate(references):
            self.variables[f"Reference{i}"] = ref
            self.variables[f"Ｒ{i}"] = ref

        self.variables['Event'] = event_name

        return self.execute_block_name(event_name)
