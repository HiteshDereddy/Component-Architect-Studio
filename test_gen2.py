import os
import sys

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_dir, "backend"))

from generator import AngularComponentGenerator
from validator import CodeValidator

model_path = os.path.join(base_dir, "backend", "models", "granite-4.1-3b-q4_k_m.gguf")
design_system_path = os.path.join(base_dir, "design-system.json")

generator = AngularComponentGenerator(model_path, design_system_path)
validator = CodeValidator(design_system_path)

prompt = """Create a full-page SaaS Analytics Dashboard layout. 
1. At the top, include a header with an .h1 title reading "Overview" and a .btn-primary button that says "Export Report". Use flexbox to separate them.
2. Below the header, create a responsive grid (1 column on mobile, 3 columns on desktop). Inside this grid, place three stat cards using the .bg-glassmorphism class. Each card should display a metric (e.g., "Total Users", "Revenue", "Active Sessions") using .h2 text colored with the primary design system color, and a small subtext description below it.
3. Below the grid, create a wide "Recent Activity" section. It should have a solid .bg-surface background, subtle rounded corners, and padding. Inside, create a simple list of 4 recent user actions using an Angular *ngFor loop over a mock array of data in the typescript file."""

print("\n--- GENERATING ---")
output = ""
for chunk in generator.generate_component_stream([], prompt):
    print(chunk, end="", flush=True)
    output += chunk

print("\n--- VALIDATING ---")
errors = validator.validate(output)
if errors:
    print("ERRORS FOUND:")
    for e in errors:
        print(f" - {e}")
else:
    print("VALIDATION PASSED")

