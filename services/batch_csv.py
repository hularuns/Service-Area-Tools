import os
import pandas as pd


def batch_csv_read(file_paths:list, low_case_cols:bool = True):
    """ Read function to read all CSVs and place into a dictionary of dataframes for subsequent analysis and joining.
    File paths should be from the parent folder onwards. Do not include C:/User etc.
    Parameters:
        file_paths (list): A list of file paths, each string should look like '/data/stored/here/mydata.csv'.
        low_case_cols (bool): If true, will convert all column names to lower case.
    """
    base_dir = os.getcwd()
    csv_loaded = {}
    for file_path in file_paths:
        filename = os.path.basename(file_path)
        key = os.path.splitext(filename)[0]
        csv_loaded[key] = pd.read_csv(base_dir+file_path)
        #converts all column names to lower case if True    
        if low_case_cols:
                    csv_loaded[key].columns.str.lower()
    return csv_loaded