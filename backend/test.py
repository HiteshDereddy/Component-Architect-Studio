import os
import time
from generator import AngularComponentGenerator
from validator import CodeValidator
from agent import AgentGraph

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_path = os.path.join(base_dir, "backend", "models", "granite-4.1-3b-q4_k_m.gguf")
    design_system_path = os.path.join(base_dir, "design-system.json")
    
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        return
        
    print("Loading LLM and Agent Graph...")
    generator = AngularComponentGenerator(model_path, design_system_path)
    validator = CodeValidator(design_system_path)
    agent_graph = AgentGraph(generator, validator)
    
    test_prompts = [
        "Create a sleek glassmorphism login card with rounded borders and a submit button using the secondary color.",
        "Build a dark theme alert banner with h3 text using the primary color.",
        "Create a simple rounded button with text 'Follow' using the primary color.",
        "Design a modern profile card with a fully rounded border, an h2 heading for the name, and a secondary color button."
    ]
    
    print("\n========================================")
    print("      STARTING AUTOMATED PROMPT TESTS     ")
    print("========================================\n")
    
    for i, prompt in enumerate(test_prompts):
        print(f"--- TEST {i+1} ---")
        print(f"Prompt: {prompt}")
        print("Status: Generating...")
        
        start_time = time.time()
        final_state = agent_graph.invoke(prompt)
        duration = time.time() - start_time
        
        print(f"Iterations taken: {final_state['iterations']}")
        if final_state['errors']:
            print(f"Final Errors: {final_state['errors']}")
        else:
            print("Validation: PASSED ✅")
            
        print(f"Time taken: {duration:.2f} seconds")
        print("Generated Code:")
        print(final_state['generated_code'][:300] + "\n...[truncated for readability]...\n")
        print("----------------------------------------\n")

if __name__ == "__main__":
    main()
