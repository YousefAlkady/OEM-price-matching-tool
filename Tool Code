import pandas as pd
from rapidfuzz import process, fuzz



#load excel files
bdeel_df = pd.read_excel("Bdeel_list.xlsx")
Rival_df = pd.read_excel("Nour.xlsx")

#reading the excel sheets
Bdeel_names = bdeel_df['Name Arabic']
Bdeel_OEM = bdeel_df['Internal Reference']
Bdeel_Price = bdeel_df['Price']

Nour_Names = Rival_df['Name']
Rival_Code1 = Rival_df['Code1']
Rival_Code2 = Rival_df['Code2']
Rival_Price = Rival_df['Price']

#Containers
Matched_Rows = []-==
Skipped_wesh = []
unMatched = []

#filter the wesh parts
filtered_Rival_Names = []
filtered_Rival_indices = []

for i, name in enumerate(Nour_Names):
    if isinstance(name, str) and "وش" in name:
        Skipped_wesh.append(["", name, "", Rival_Code1[i],Rival_Code2[i],"","", "Skipped"])
    else:
        filtered_Rival_Names.append(name)
        filtered_Rival_indices.append(i)

#match bdeel part names to Nour names

for i, part in enumerate(Bdeel_names):
    if pd.isna(part) or not isinstance(part, str) or not part.strip():
        continue

    match_result = process.extractOne(part, filtered_Rival_Names, scorer=fuzz.token_sort_ratio)
    if match_result is None:
        continue

    match, score, idx = match_result
    if score >= 75:
        matched_index = filtered_Rival_indices[idx]

        Matched_Rows.append([
            part,  # Bdeel Part Name
            filtered_Rival_Names[idx],  # Matched Nour Name
            Bdeel_OEM[i],  # Bdeel OEM
            Rival_Code1[matched_index],  # Correct Nour Code 1
            Rival_Code2[matched_index],  # Correct Nour Code 2
            Bdeel_Price[i],  # Bdeel Price
            Rival_Price[matched_index],  # Nour Price
            score  # Match score
        ])

full_data = Matched_Rows + Skipped_wesh

Rival_Company = input("Rival Company Name: ")

final_df = pd.DataFrame(full_data, columns = ["Bdeel Part Name", Rival_Company, "OEM Number","Rival Code1", "Rival Code2", "Bdeel Price", "Rival Price", "Match Score"])
final_df.to_excel("Mapped_OEM_Parts.xlsx", index=False)

print("Done!")
