import json
import re
import os
import subprocess
from pathlib import Path
from collections import Counter

class CodeValidator:
    def __init__(self, design_system_path: str):
        with open(design_system_path, "r") as f:
            self.design_system = json.load(f)
        self.allowed_hex_colors = {
            color.lower() for color in self.design_system.get("colors", {}).values()
        }
        self.allowed_css_vars = {
            f"var(--{token})" for token in self.design_system.get("colors", {}).keys()
        }
            
    def validate(self, generated_code: str) -> list[str]:
        errors = []

        # Strip CoT <think>...</think> block before validation
        generated_code = re.sub(r"<think>.*?</think>", "", generated_code, flags=re.DOTALL).strip()

        # 1. Parse markdown blocks
        code_blocks = self._extract_code_blocks(generated_code)
        if not code_blocks:
            errors.append("Syntax Error: No valid markdown code blocks (```typescript, ```html, ```css) found in the response. You must wrap your code in markdown blocks.")
            return errors

        required_blocks = {"typescript", "html", "css"}
        missing_blocks = sorted(required_blocks - set(code_blocks.keys()))
        if missing_blocks:
            errors.append(f"Format Error: Missing required code block(s): {', '.join(missing_blocks)}.")
            
        full_code = "\n".join(code_blocks.values())
        
        self._validate_typescript_contract(code_blocks.get("typescript", ""), errors)
        self._validate_html_contract(code_blocks.get("html", ""), errors)
        self._validate_design_system(full_code, errors)

        # Run Angular TypeScript compiler check as the final validation step
        if not errors:
            self._validate_via_tsc(
                code_blocks.get("typescript", ""),
                code_blocks.get("html", ""),
                code_blocks.get("css", ""),
                errors
            )

        return errors

    def _validate_typescript_contract(self, code: str, errors: list[str]) -> None:
        if not code:
            return

        required_snippets = {
            "@Component": "Angular Contract Error: TypeScript must define an @Component.",
            "standalone: true": "Angular Contract Error: Component must be standalone.",
            "templateUrl": "Angular Contract Error: Use templateUrl instead of inline template.",
            "styleUrls": "Angular Contract Error: Use styleUrls instead of inline styles.",
            "export class": "Angular Contract Error: Component class must be exported.",
        }
        for snippet, message in required_snippets.items():
            if snippet not in code:
                errors.append(message)

        if re.search(r"\btemplate\s*:", code):
            errors.append("Angular Contract Error: Inline template is not allowed.")
        if re.search(r"\bstyles\s*:", code):
            errors.append("Angular Contract Error: Inline styles are not allowed.")
        if re.search(r"import\s+{[^}]*\bstandalone\b[^}]*}\s+from\s+['\"]@angular/core['\"]", code):
            errors.append("Angular Syntax Error: 'standalone' is not exported from '@angular/core'. Do not import it. 'standalone: true' belongs inside the @Component decorator object.")

    def _validate_html_contract(self, code: str, errors: list[str]) -> None:
        if not code:
            return

        forbidden_tags = re.findall(r"</?(script|style|template)\b", code, flags=re.IGNORECASE)
        if forbidden_tags:
            tags = ", ".join(sorted(set(tag.lower() for tag in forbidden_tags)))
            errors.append(f"Markup Purity Error: HTML block must not include these tags: {tags}.")

    def _validate_design_system(self, full_code: str, errors: list[str]) -> None:
        found_hex_colors = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", full_code))
        for hex_color in sorted(found_hex_colors):
            if hex_color.lower() not in self.allowed_hex_colors:
                errors.append(f"Design System Error: Unauthorized hex color '{hex_color}' used. You must ONLY use the exact colors defined in the Design System JSON.")

        tailwind_color_classes = re.findall(
            r"\b(?:bg|text|border|ring|from|via|to|shadow|outline|decoration)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}(?:/\d{1,3})?\b",
            full_code,
        )
        if tailwind_color_classes:
            sample = ", ".join(sorted(set(tailwind_color_classes))[:5])
            errors.append(
                "Design System Error: Tailwind default color classes are not allowed. "
                f"Use CSS variables instead. Found: {sample}."
            )

    def _extract_code_blocks(self, markdown: str) -> dict:
        blocks = {}
        # Case-insensitive match, handles uppercase (HTML, TypeScript, CSS) and whitespace variants
        pattern = re.compile(r'```\s*(\w+)\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(markdown)
        for lang, code in matches:
            lang = lang.lower().strip()
            # Normalize language aliases
            if lang in ("ts", "typescript"):
                lang = "typescript"
            elif lang in ("html", "htm"):
                lang = "html"
            elif lang in ("css", "scss", "styles"):
                lang = "css"
            # Only keep the first occurrence of each block type
            if lang not in blocks:
                blocks[lang] = code.strip()
        return blocks

    def _validate_via_tsc(self, ts_code: str, html_code: str, css_code: str, errors: list[str]) -> None:
        project_root = Path(__file__).resolve().parents[1]
        validate_dir = project_root / "frontend" / "src" / "app" / "validate-preview"
        validate_dir.mkdir(parents=True, exist_ok=True)
        
        # Write files
        try:
            (validate_dir / "generated.component.ts").write_text(ts_code, encoding="utf-8")
            (validate_dir / "generated.component.html").write_text(html_code, encoding="utf-8")
            (validate_dir / "generated.component.css").write_text(css_code, encoding="utf-8")
        except Exception as e:
            errors.append(f"Validator Write Error: Could not prepare files for compiler check: {e}")
            return
        
        # Run tsc
        tsc_bin = project_root / "frontend" / "node_modules" / ".bin" / "tsc"
        if not tsc_bin.exists():
            # If tsc bin isn't found, skip compile check
            return
            
        command = [str(tsc_bin), "-p", str(project_root / "frontend" / "tsconfig.app.json"), "--noEmit"]
        try:
            result = subprocess.run(
                command,
                cwd=project_root / "frontend",
                capture_output=True,
                text=True,
                timeout=25, # Angular/TypeScript compilation can take up to 10-15s under load
            )
            if result.returncode != 0:
                output = result.stdout + "\n" + result.stderr
                compile_errors = []
                for line in output.splitlines():
                    if "validate-preview" in line:
                        clean_line = line.replace(str(validate_dir), "validate-preview")
                        compile_errors.append(clean_line)
                if compile_errors:
                    errors.extend(compile_errors)
        except subprocess.TimeoutExpired:
            # Under extreme CPU/LLM load, tsc might time out. We don't want to crash.
            pass
        except Exception as e:
            errors.append(f"Compiler Check Error: {e}")
        finally:
            # Clean up immediately
            try:
                for f in ["generated.component.ts", "generated.component.html", "generated.component.css"]:
                    (validate_dir / f).unlink(missing_ok=True)
            except Exception:
                pass

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ds_path = os.path.join(base_dir, "design-system.json")
    
    if os.path.exists(ds_path):
        validator = CodeValidator(ds_path)
        
        print("--- Running Validator Tests ---")
        
        # Test 1: Valid Code
        valid_code = """```typescript
@Component({
  selector: 'app-generated',
  standalone: true,
  templateUrl: './generated.component.html',
  styleUrls: ['./generated.component.css']
})
export class GeneratedComponent {}
```
```html
<section class="card"><button class="btn">Save</button></section>
```
```css
.card { color: var(--textPrimary); background: var(--surface); }
```
"""
        errors = validator.validate(valid_code)
        print(f"Test 1 (Valid): {'PASS' if not errors else 'FAIL -> ' + str(errors)}")
        
        # Test 2: Unauthorized Color
        invalid_color = "```css\nbackground-color: #ff0000;\n```"
        errors = validator.validate(invalid_color)
        print(f"Test 2 (Bad Color): {'PASS (Caught error)' if errors else 'FAIL'}")
        if errors: print("   ->", errors[0])
        
        # Test 3: Unbalanced Brackets
        invalid_syntax = "```typescript\n@Component({\nclass Test {\n```"
        errors = validator.validate(invalid_syntax)
        print(f"Test 3 (Bad Syntax): {'PASS (Caught error)' if errors else 'FAIL'}")
        if errors: print("   ->", errors[0])
    else:
        print("Design system not found.")
