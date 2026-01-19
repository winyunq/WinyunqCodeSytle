import os

def verify_skills():
    skills_path = ".agent/skills"
    required_skills = [
        "WinyunqCore",
        "RosCppNavigation",
        "PythonImuAnalysis",
        "Ue5Simulation"
    ]
    
    print(f"--- Verifying Agent Skills in {os.path.abspath(skills_path)} ---")
    
    if not os.path.exists(skills_path):
        print(f"[ERROR] Skills directory not found: {skills_path}")
        return

    for skill in required_skills:
        skill_dir = os.path.join(skills_path, skill)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        
        if os.path.isdir(skill_dir):
            if os.path.exists(skill_md):
                print(f"[SUCCESS] Skill '{skill}' is correctly initialized.")
            else:
                print(f"[WARNING] Skill '{skill}' directory exists, but SKILL.md is missing.")
        else:
            print(f"[ERROR] Skill '{skill}' directory is missing.")

if __name__ == "__main__":
    verify_skills()
