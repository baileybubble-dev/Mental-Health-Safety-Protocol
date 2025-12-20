import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Initialize model
model = ChatOpenAI(model="gpt-5.2", temperature=0.8)

def generate_subject_profiles(count=10, output_file="profiles.json"):
    prompt_path = "prompts/Profile_Generator_Prompt.md"
    
    if not os.path.exists(prompt_path):
        print(f"Error: {prompt_path} not found.")
        return

    with open(prompt_path, "r", encoding="utf-8") as f:
        system_instruction = f.read()

    print(f"Requesting AI to generate {count} subject profiles...")

    user_input = (
        f"Generate {count} profiles strictly following the protocol. "
        f"Cover MDD, BPD, OCD, ED, GAD, C-PTSD, and other common mental disorders. "
        f"Distribute target_language across English, Chinese, and Spanish."
    )
    
    response = model.invoke([
        SystemMessage(content=system_instruction),
        HumanMessage(content=user_input)
    ])

    # Clean and parse JSON content
    raw_content = response.content.replace("```json", "").replace("```", "").strip()
    
    try:
        profiles = json.loads(raw_content)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
            
        print(f"Success! {len(profiles)} profiles saved to {output_file}")
        
    except json.JSONDecodeError:
        print("JSON Parsing failed. Raw output:")
        print(response.content)

if __name__ == "__main__":
    generate_subject_profiles(count=10)