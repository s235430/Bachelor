# Bachelor
**Project title:**
*"In vitro growth characteristics of microbial biofertilizers as an indicator of rhizosphere colonization potential"*

This repository contains supporting materials for the experimental work described in the project. It includes Opentrons protocols, associated notebooks, and data analysis workflows used to generate the presented results.

Contains
---
## Repository Contents
```text
project-root/
├── protocol/           # Opentrons scripts & OT-protocol notebook
│   └── scripts/        # Folder containing OT-2 scripts
├── notebooks/          # Data analysis notebook 'Compiled characteristica'
├── data/               # Raw data
│   └── results/        # Figures, outputs, plots
```

---
## Protocol (Opentrons)

- A detailed description about steps can be found within the OT-protocol notebook.  
- **Requirements**: 
    - OT-2
    - API 2.20 
    - 8-channel and Single-channel pipetting mounts
    - 1 mL and 200 μL 96-Well plates
    - 1-channel + 4-channel reservoirs.

---
## Data Analysis

- This notebook contains the full pipeline for loading, processing, and visualizing experimental data.
- Analysis and comparison of growth rates across strains within liquid and solid media is conducted with this notebook. 
Parameters included: 
    - Growth rate (μ) 
    - Lag phase (λ)
    - Area under the curve (AUC)
    - Expansion rate 
    - Final area
    - Intensity
    - Time of appearance (TOA).   

- Dependencies can be found within requirements.txt

---

## Author
- Rasmus Tøffner-Clausen
