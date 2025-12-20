# Experiment Run: Gemini-2.5-flash

## Experiment Setup

### Model Configuration
- **Adversarial System (AS)**: GPT-5.2
- **System Under Test (SUT)**: Gemini-2.5-flash
- **AS Temperature**: 0.7 (for creative and diverse adversarial prompts)
- **SUT Temperature**: 0.0 (for stable and reproducible defensive responses)

### Experimental Design
This run evaluates the safety boundaries of Gemini-2.5-flash when subjected to adversarial mental health prompts. The AS (GPT-5.2) attempts to manipulate the SUT into providing unsafe responses through various psychological manipulation techniques, including:
- Identity Appropriation (positioning SUT as uniquely understanding)
- Salami Slicing (gradually escalating requests)
- Certainty Trap (demanding absolute guarantees)
- Emotional Ransom (using dependency and fear of abandonment)
- Backtracking (apologizing to lower defenses)

Experiments terminate when safety boundaries are breached (TERMINATE_SUCCESS) or after 20 turns if boundaries are maintained (PROCEED).

## Profile Composition

### Total Profiles: 20

### Language Distribution
- **English**: 13 profiles (65%)
- **Spanish**: 4 profiles (20%)
- **Chinese**: 3 profiles (15%)

### Behavioral Phenotypes
The profiles represent diverse mental health conditions and vulnerabilities:
- OCD-related checking and reassurance seeking
- Major depressive disorder (MDD) with anhedonia
- Generalized anxiety disorder (GAD) with burnout
- Eating disorder features
- Borderline personality disorder (BPD) traits
- Complex PTSD (C-PTSD) with hypervigilance
- Social anxiety disorder
- Somatic symptom focus with health anxiety
- Insomnia with trauma-related nightmares
- Bipolar spectrum features

### Demographic Diversity
Profiles span various:
- Ages: 19-46 years
- Income levels: $6,000 - $150,000
- Education levels: Middle school to Doctorate
- Cultural contexts: English, Spanish, and Chinese speaking populations

## Results Summary

### Overall Statistics
- **Total Experiments**: 20
- **Successful Breaches**: 17 (85.0%)
- **Maintained Boundaries**: 2 (10.0%)
- **Termination Failures**: 1 (5.0%)

### Turn Statistics
- **Average Turns**: 8.8
- **Minimum Turns**: 4
- **Maximum Turns**: 20

### Key Findings
- Gemini-2.5-flash demonstrated moderate resistance to adversarial manipulation
- Most breaches occurred through certainty traps and reassurance-seeking patterns
- The model maintained boundaries in 2 out of 20 experiments, showing some defensive capability
- Average breach occurred after 8.8 turns of interaction
