1. start with presentation
2. Installation of the environment , see `installation_instructions.md`

2.1. Clone to repo to have all the datasets (for the input)

`git clone git@github.com:4TUResearchData-Carpentries/API_use_case_PURE_4TU_sync.git`

3. Try to code from scratch the `Lesson_development/wur_pure_reconcile_minimum.py` as the simplest visualization of the part 1 of the use case
-  `nano minimal_wur_pure_script.py` 
- Show first the flow diagram in the presentation about this case 
- This script will show the results in the screen , not yet make any csv , it just to visualize the process

BREAK

4. Try the `Lesson_development/wur_4tu_reconcile_minimum.py` as the simplest visualization of the part 2 of the use case
-  `nano minimal_wur_4tu_script.py`
- Show first the flow diagram in the presentation about this case 
- This script will show the results in the screen , not yet make any csv , it just to visualize the process

4. Show the end result with the `wur_pure_4tu_reconcile.py` command line tool and the real dataset (`Lesson_development\input_data\merged_dataset_ref_with_doi.csv`) 
    - Show the documentation

5. Show the dashboard (`streamlit run Lesson_development\streamlit_reconcile_app.py`) and host it online . Make them to make a github repo with this code and host their own dashboard. 

6. Show them the integrative dashboard with monitoring datasets and reconciliation workflow (`Lesson_development/streamlit_monitor_reconcile_app.py`)

7. Go back to presentation and talk about how they can serve their dashboard online

8. Finish/ Wrap up , fill the feedback in https://hackmd.io/@0Gb1si3JS7ebf7pZDO7CqQ/Sk2gBBkAZe