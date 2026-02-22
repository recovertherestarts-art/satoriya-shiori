import json
import os
import glob
import sys
import re
from core.parser import parse_dict_file
from core.interpreter import SatoriInterpreter

def load_all_dictionaries(ghost_path):
    # Dictionaries are in ghost/master/dic*.txt
    dic_path = os.path.join(ghost_path, "ghost/master")
    if not os.path.exists(dic_path):
        # Maybe it's directly in the ghost_path
        dic_path = ghost_path

    dic_files = glob.glob(os.path.join(dic_path, "dic*.txt"))
    # Also include replace.txt etc if needed, but for logic dic*.txt is priority

    all_blocks = []
    for f in dic_files:
        try:
            all_blocks.extend(parse_dict_file(f))
        except Exception as e:
            print(f"Warning: Failed to parse {f}: {e}")
    return all_blocks

class SatoriTestRunner:
    def __init__(self, ghost_path):
        self.ghost_path = ghost_path
        self.interpreter = SatoriInterpreter()
        blocks = load_all_dictionaries(ghost_path)
        self.interpreter.load_blocks(blocks)

    def run_test_case(self, test_case):
        event = test_case.get('event', 'OnTest')
        refs = test_case.get('references', [])
        expected = test_case.get('expected', None)
        mocks = test_case.get('mocks', {})

        # Apply mocks
        if 'variables' in mocks:
            self.interpreter.variables.update(mocks['variables'])
        if 'saori' in mocks:
            self.interpreter.saori_mocks = mocks['saori']

        # Reset scope for each test
        self.interpreter.current_scope = 1

        try:
            output = self.interpreter.run_event(event, refs)
            error = None
        except Exception as e:
            output = ""
            error = str(e)

        result = {
            'name': test_case.get('name', event),
            'event': event,
            'output': output,
            'passed': True,
            'reason': '',
            'error': error
        }

        if error:
            result['passed'] = False
            result['reason'] = f"Execution error: {error}"
            return result

        if expected is not None:
            if isinstance(expected, str):
                # Check for regex if it starts and ends with /
                if expected.startswith('/') and expected.endswith('/'):
                    pattern = expected[1:-1]
                    if not re.search(pattern, output):
                        result['passed'] = False
                        result['reason'] = f"Output did not match regex '{pattern}'"
                elif expected not in output:
                    result['passed'] = False
                    result['reason'] = f"Expected string '{expected}' not found in output"
            elif isinstance(expected, list):
                for e in expected:
                    # Same regex logic for list items
                    if e.startswith('/') and e.endswith('/'):
                        pattern = e[1:-1]
                        if not re.search(pattern, output):
                            result['passed'] = False
                            result['reason'] = f"Output did not match regex '{pattern}'"
                            break
                    elif e not in output:
                        result['passed'] = False
                        result['reason'] = f"Expected string '{e}' not found in output"
                        break

        expected_vars = test_case.get('expected_variables', {})
        for var, val in expected_vars.items():
            actual_val = self.interpreter.variables.get(var)
            if actual_val != val:
                result['passed'] = False
                result['reason'] = f"Variable '{var}' expected '{val}' but got '{actual_val}'"
                break

        return result

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 runner.py <ghost_path> <test_json_file>")
        return

    ghost_path = sys.argv[1]
    test_file = sys.argv[2]

    with open(test_file, 'r', encoding='utf-8') as f:
        tests = json.load(f)

    runner = SatoriTestRunner(ghost_path)
    print(f"Loaded {len(runner.interpreter.sentences)} sentences and {len(runner.interpreter.word_groups)} word groups.")

    passed_count = 0
    results = []
    for test in tests:
        res = runner.run_test_case(test)
        results.append(res)
        if res['passed']:
            passed_count += 1
            print(f"PASS: {res['name']}")
        else:
            print(f"FAIL: {res['name']} - {res['reason']}")
            print(f"  Output: {res['output']}")

    print(f"\nSummary: {passed_count}/{len(tests)} passed.")

if __name__ == "__main__":
    main()
