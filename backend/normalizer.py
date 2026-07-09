import re
import json
import os

# Load design system to know exact token names for CSS variable fixing
_DS_PATH = os.path.join(os.path.dirname(__file__), "..", "design-system.json")
try:
    with open(_DS_PATH) as f:
        _DESIGN_SYSTEM = json.load(f)
except Exception:
    _DESIGN_SYSTEM = {"colors": {}, "spacing": {}, "borders": {}}

# Build the canonical set of CSS variables from the design system
_VALID_CSS_VARS = set()
for k in _DESIGN_SYSTEM.get("colors", {}):
    _VALID_CSS_VARS.add(f"--{k}")
for k in _DESIGN_SYSTEM.get("spacing", {}):
    _VALID_CSS_VARS.add(f"--spacing-{k}")
for k in _DESIGN_SYSTEM.get("borders", {}):
    _VALID_CSS_VARS.add(f"--border-{k}")

# Map hallucinated CSS variable names -> real design system token names
_CSS_VAR_FIXES = {
    # Spacing hallucinations
    "--space-xs": "--spacing-small",
    "--space-s": "--spacing-small",
    "--space-sm": "--spacing-small",
    "--space-m": "--spacing-medium",
    "--space-md": "--spacing-medium",
    "--space-l": "--spacing-large",
    "--space-lg": "--spacing-large",
    "--spacing-xs": "--spacing-small",
    "--spacing-sm": "--spacing-small",
    "--spacing-md": "--spacing-medium",
    "--spacing-lg": "--spacing-large",
    "--spacing-xl": "--spacing-large",
    "--gap": "--spacing-medium",
    "--padding": "--spacing-medium",
    "--margin": "--spacing-medium",
    # Color hallucinations
    "--text-primary": "--textPrimary",
    "--text-secondary": "--textSecondary",
    "--color-primary": "--primary",
    "--color-secondary": "--secondary",
    "--color-background": "--background",
    "--color-surface": "--surface",
    "--bg": "--background",
    "--bg-color": "--background",
    "--surface-color": "--surface",
    # Border hallucinations
    "--border-radius": "--border-radius",
    "--radius": "--border-radius",
    "--border-radius-sm": "--border-radius",
    "--border-radius-lg": "--border-radiusLarge",
    "--border-radius-full": "--border-radiusFull",
    "--rounded": "--border-radius",
}

STANDARD_FALLBACKS = {
    "CommonModule": "@angular/common",
    "FormsModule": "@angular/forms",
    "ReactiveFormsModule": "@angular/forms",
    "RouterModule": "@angular/router",
    "RouterOutlet": "@angular/router",
}

IMPORTS_MAP = {
    "MatCardModule": ("@angular/material/card", [r"</?mat-card\b", r"</?mat-card-"]),
    "MatButtonModule": ("@angular/material/button", [
        r"\bmat-button\b", r"\bmat-raised-button\b", r"\bmat-flat-button\b",
        r"\bmat-stroked-button\b", r"\bmat-icon-button\b", r"\bmat-fab\b", r"\bmat-mini-fab\b"
    ]),
    "MatFormFieldModule": ("@angular/material/form-field", [r"</?mat-form-field\b"]),
    "MatInputModule": ("@angular/material/input", [r"\bmatInput\b"]),
    "MatIconModule": ("@angular/material/icon", [r"</?mat-icon\b"]),
    "MatCheckboxModule": ("@angular/material/checkbox", [r"</?mat-checkbox\b"]),
    "MatRadioModule": ("@angular/material/radio", [r"</?mat-radio-"]),
    "MatSelectModule": ("@angular/material/select", [r"</?mat-select\b"]),
    "MatSlideToggleModule": ("@angular/material/slide-toggle", [r"</?mat-slide-toggle\b"]),
    "MatSliderModule": ("@angular/material/slider", [r"</?mat-slider\b"]),
    "MatMenuModule": ("@angular/material/menu", [r"</?mat-menu\b"]),
    "MatDividerModule": ("@angular/material/divider", [r"</?mat-divider\b"]),
    "MatProgressSpinnerModule": ("@angular/material/progress-spinner", [r"</?mat-spinner\b", r"</?mat-progress-spinner\b"]),
    "MatProgressBarModule": ("@angular/material/progress-bar", [r"</?mat-progress-bar\b"]),
    "MatTabsModule": ("@angular/material/tabs", [r"</?mat-tab-group\b", r"</?mat-tab\b"]),
    "MatToolbarModule": ("@angular/material/toolbar", [r"</?mat-toolbar\b"]),
    "MatListModule": ("@angular/material/list", [r"</?mat-list\b", r"</?mat-list-item\b"]),
    "FormsModule": ("@angular/forms", [r"\[\([^)]+\)\]\s*=\s*", r"\bngModel\b"]),
    "CommonModule": ("@angular/common", [r"\*(ngIf|ngFor|ngSwitch)\b"]),
}


def get_material_import_path(module_name: str) -> str:
    component_name = module_name[3:-6]
    kebab = re.sub(r'(?<!^)(?=[A-Z])', '-', component_name).lower()
    return f"@angular/material/{kebab}"


def get_import_path_for_module(module_name: str) -> str | None:
    if module_name in STANDARD_FALLBACKS:
        return STANDARD_FALLBACKS[module_name]
    if module_name.startswith("Mat") and module_name.endswith("Module"):
        return get_material_import_path(module_name)
    return None


def fix_css_variables(css_code: str) -> str:
    """Replaces hallucinated CSS variable names with correct design system token names."""
    def replace_var(m):
        var_name = m.group(1)
        corrected = _CSS_VAR_FIXES.get(var_name)
        if corrected:
            return f"var({corrected})"
        # If the variable name is completely unknown and not in design system, replace with a safe fallback
        if var_name not in _VALID_CSS_VARS:
            # Try to guess a good replacement
            if "primary" in var_name:
                return "var(--primary)"
            if "secondary" in var_name:
                return "var(--secondary)"
            if "background" in var_name or "bg" in var_name:
                return "var(--background)"
            if "surface" in var_name:
                return "var(--surface)"
            if "text" in var_name or "color" in var_name:
                return "var(--textPrimary)"
            if "space" in var_name or "gap" in var_name or "padding" in var_name or "margin" in var_name:
                return "var(--spacing-medium)"
            if "radius" in var_name or "rounded" in var_name:
                return "var(--border-radius)"
        return m.group(0)  # Already valid, keep as-is

    return re.sub(r"var\((--[\w-]+)\)", replace_var, css_code)


def strip_input_decorators(ts_code: str) -> str:
    """Removes @Input() decorators from component class properties.
    Components must be self-contained - they cannot rely on parent input.
    """
    # Remove @Input() decorator from class properties
    code = re.sub(r"\s*@Input\(\)\s*", "\n  ", ts_code)
    # Remove Input from @angular/core imports
    code = re.sub(r",?\s*\bInput\b\s*,?", "", code)
    # Clean up empty import braces like: import {  } from '@angular/core'
    code = re.sub(r"import\s*\{\s*\}\s*from\s*'[^']*';\n?", "", code)
    # Fix double commas or trailing commas in imports from cleanup
    code = re.sub(r"\{\s*,\s*", "{ ", code)
    code = re.sub(r",\s*\}", " }", code)
    return code


def normalize_ts_code(ts_code: str, html_code: str) -> str:
    code = ts_code.strip()

    # 1. Standard overrides - canonical paths and class name
    code = re.sub(r"selector\s*:\s*['\"][^'\"]+['\"]", "selector: 'app-generated-component'", code)
    code = re.sub(r"templateUrl\s*:\s*['\"][^'\"]+['\"]", "templateUrl: './generated.component.html'", code)
    code = re.sub(r"styleUrls\s*:\s*\[[^\]]*\]", "styleUrls: ['./generated.component.css']", code, flags=re.DOTALL)
    code = re.sub(r"export\s+class\s+\w+", "export class GeneratedComponent", code, count=1)

    # 2. Strip @Input() decorators - components must be standalone and self-contained
    code = strip_input_decorators(code)

    # 3. Deduce modules needed from HTML
    needed_modules = {}
    for module_name, (import_path, patterns) in IMPORTS_MAP.items():
        for pattern in patterns:
            if re.search(pattern, html_code):
                needed_modules[module_name] = import_path
                break

    if not needed_modules:
        needed_modules["CommonModule"] = "@angular/common"

    # 4. Add modules already imported at file level
    file_level_imports = set(re.findall(r"\b(\w+Module)\b", re.sub(r"@Component\(.*?\)", "", code, flags=re.DOTALL)))
    for mod in file_level_imports:
        if mod not in needed_modules:
            path = get_import_path_for_module(mod)
            if path:
                needed_modules[mod] = path

    # 5. Sync @Component decorator imports array
    decorator_match = re.search(r"(@Component\s*\(\s*({.*?})\s*\))", code, flags=re.DOTALL)
    if decorator_match:
        full_decorator, decorator_content = decorator_match.group(1), decorator_match.group(2)
        imports_match = re.search(r"\bimports\s*:\s*\[(.*?)\]", decorator_content, flags=re.DOTALL)

        if imports_match:
            current_imports = imports_match.group(1)
            imported_list = [imp.strip() for imp in current_imports.split(",") if imp.strip()]
            for module_name in needed_modules:
                if module_name not in imported_list:
                    imported_list.append(module_name)
            for imp in imported_list:
                if imp.endswith("Module") and imp not in needed_modules:
                    path = get_import_path_for_module(imp)
                    if path:
                        needed_modules[imp] = path
            new_imports_str = f"imports: [{', '.join(imported_list)}]"
            new_decorator_content = re.sub(r"\bimports\s*:\s*\[.*?\]", new_imports_str, decorator_content, flags=re.DOTALL)
            new_decorator = full_decorator.replace(decorator_content, new_decorator_content)
            code = code.replace(full_decorator, new_decorator)
        else:
            if "standalone: true" in decorator_content:
                new_decorator_content = re.sub(
                    r"(standalone\s*:\s*true\s*,?)",
                    f"\\1\n  imports: [{', '.join(needed_modules.keys())}],",
                    decorator_content, count=1
                )
                new_decorator = full_decorator.replace(decorator_content, new_decorator_content)
                code = code.replace(full_decorator, new_decorator)

    # 6. Inject missing file-level ES6 imports
    for module_name, import_path in needed_modules.items():
        if not re.search(rf"\bimport\s+{{[^}}]*\b{module_name}\b[^}}]*}}\s+from", code):
            code = f"import {{ {module_name} }} from '{import_path}';\n" + code

    return code + "\n"


def normalize_markdown_code(markdown: str) -> str:
    # Strip Chain-of-Thought <think>...</think> block before processing
    markdown = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL).strip()

    blocks = {}
    pattern = re.compile(r'```\s*(\w+)\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)
    for language, code in pattern.findall(markdown):
        lang = language.lower().strip()
        if lang in ("ts", "typescript"):
            lang = "typescript"
        elif lang in ("html", "htm"):
            lang = "html"
        elif lang in ("css", "scss", "styles"):
            lang = "css"
        if lang not in blocks:
            blocks[lang] = code.strip()

    ts_code = blocks.get("typescript", "")
    html_code = blocks.get("html", "")
    css_code = blocks.get("css", "")

    if not ts_code or not html_code:
        return markdown

    normalized_ts = normalize_ts_code(ts_code, html_code)
    fixed_css = fix_css_variables(css_code)

    return (
        f"```typescript\n{normalized_ts}```\n\n"
        f"```html\n{html_code}\n```\n\n"
        f"```css\n{fixed_css}\n```"
    )
