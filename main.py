import streamlit as st
import pandas as pd
import os
from simple_salesforce import Salesforce
from google.cloud import secretmanager
import json
import jellyfish
from time import sleep, strftime

# Define a temporary folder for storing uploaded and generated files
TEMP_FOLDER = "temp"
os.makedirs(TEMP_FOLDER, exist_ok=True)
timestr = strftime("%Y%m%d_%H%M%S_")

# Streamlit UI
st.title("Salesforce Acquisition Duplicate Processing Tool")

# Key uploader
Key_file = st.file_uploader("📂 Upload Key File", type=["json"])

# Set the path dynamically only after the file is uploaded
if Key_file:
    Key_path = os.path.join(TEMP_FOLDER, Key_file.name)
    with open(Key_path, "wb") as f:
        f.write(Key_file.getbuffer())

    # Now that the file exists, set the environment variable
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = Key_path
    st.success(f"✅ Key file saved and environment variable set!")

# Function to generate the template Excel file
def generate_excel():
    Acquisition_Column_List = [
        "Legacy Customer ID",
        "Payment Terms",
        "Account Name",
        "Billing Street",
        "Billing Address Line 2",
        "Billing City",
        "Billing State/Province",
        "Billing Zip/Postal Code",
        "Billing Country",
        "Tax ID",
    ]
    Acquisition_Template = pd.DataFrame(columns=Acquisition_Column_List)
    filepath = os.path.join(TEMP_FOLDER, "Acquisition_Template.xlsx")
    Acquisition_Template.to_excel(filepath, index=False)
    return filepath


# Generate and store the template Excel file in TEMP_FOLDER
excel_file = generate_excel()

# Streamlit download button for the template file
st.download_button(
    label="📥 Download Template",
    data=open(excel_file, "rb").read(),
    file_name=timestr + "Acquisition_Template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# File uploaders
acquisition_file = st.file_uploader("📂 Upload Acquisition File", type=["xlsx"])


# Save uploaded files into the temp folder
acquisition_path = None
salesforce_path = None

if acquisition_file:
    acquisition_path = os.path.join(TEMP_FOLDER, acquisition_file.name)
    with open(acquisition_path, "wb") as f:
        f.write(acquisition_file.getbuffer())
    st.success(f"✅ Acquisition file saved")


# **Automatically preprocess Acquisition file when uploaded**
if acquisition_file:
    st.write("🔄 Processing Acquisition file...")

    # Read and preprocess the acquisition file
    Acquisition_Data = pd.read_excel(acquisition_path)

    # Ensure necessary columns exist
    required_columns = ["Billing Street", "Billing Address Line 2"]
    for col in required_columns:
        if col not in Acquisition_Data.columns:
            st.error(f"⚠️ Missing column in Acquisition file: {col}")
            st.stop()

    # Apply preprocessing steps automatically
    Copy_Acquisition_Data = Acquisition_Data[required_columns].replace(
        r"(?i)Att.*$", "", regex=True
    )
    Acquisition_Data["FullAddress"] = Copy_Acquisition_Data.apply(
        lambda x: "\n".join(x.dropna().astype(str)), axis=1
    )

    # Save the preprocessed file in the temp folder
    processed_acquisition_path = os.path.join(TEMP_FOLDER, "processed_acquisition.xlsx")
    Acquisition_Data.to_excel(processed_acquisition_path, index=False)

    st.success("✅ Acquisition file preprocessed and ready for further processing!")
    st.download_button(
        label="📥 Download Processed Acquisition File",
        data=open(processed_acquisition_path, "rb").read(),
        file_name=timestr + "processed_acquisition.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# Function to retrieve secrets
def get_secret(secret_id, project_id="selesforce-455620"):
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

    response = client.access_secret_version(request={"name": secret_name})
    secret_data = response.payload.data.decode("UTF-8")

    return json.loads(secret_data)  # Convert JSON string to Python dictionary


st.title("🔐 Salesforce Login")

# Salesforce environment
environment = "PROD"

# Input fields for username and password
SF_UserName = st.text_input("🔄 Salesforce User Name")
SF_Password = st.text_input("🔄 Salesforce Password", type="password")

# Button to authenticate and store `sf` globally
if st.button("🔐 Login"):
    try:
        # Retrieve secrets from Google Cloud
        secrets = get_secret("Salesforce_Key", "selesforce-455620")

        # Get credentials for the selected environment
        env_data = secrets.get(environment, {})
        URL = env_data.get("url")
        KEY = env_data.get("key")
        SECRET = env_data.get("secret")

        # Validate retrieved credentials
        if not URL or not KEY or not SECRET:
            st.error(f"⚠️ Missing credentials for {environment}")
        else:
            # Authenticate with Salesforce
            st.session_state.sf = Salesforce(
                username=SF_UserName,
                instance_url=URL,
                password=SF_Password,
                consumer_key=KEY,
                consumer_secret=SECRET,
            )
            st.success(f"✅ Successfully authenticated to {environment}!")
    except Exception as e:
        st.error(f"❌ Authentication failed: {str(e)}")


# Function to fetch and clean Salesforce results
def fetch_and_clean_results(Currency):
    """Fetch Salesforce data and clean column names."""
    if "sf" not in st.session_state:
        st.error("⚠️ You must log in first!")
        return None

    sf = st.session_state.sf  # Retrieve the stored Salesforce session

    query = f"""
        SELECT 
            Id, Enterprise_ID__c, Name, BillingStreet, BillingCity, BillingState, 
            BillingPostalCode, BillingCountry,
            DNBConnect__D_B_Connect_Company_Profile__r.primAddr_streetAddr_line1__c,
            DNBConnect__D_B_Connect_Company_Profile__r.primAddr_AddrLocal_name__c,
            DNBConnect__D_B_Connect_Company_Profile__r.primAddr_Region_name__c, 
            DNBConnect__D_B_Connect_Company_Profile__r.primAddr_postalCode__c, 
            DNBConnect__D_B_Connect_Company_Profile__r.primAddr_Cntry_name__c, 
            DNBConnect__D_B_Connect_Company_Profile__r.mailingAddr_streetAddr_line1__c,
            DNBConnect__D_B_Connect_Company_Profile__r.mailingAddr_AddrLocal_name__c, 
            DNBConnect__D_B_Connect_Company_Profile__r.mailingAddr_Region_name__c,
            DNBConnect__D_B_Connect_Company_Profile__r.mailingAddr_postalCode__c, 
            DNBConnect__D_B_Connect_Company_Profile__r.mailingAddr_Cntry_name__c
        FROM Account
        WHERE RecordType.Name IN ('Customer', 'Prospect') 
        AND CurrencyIsoCode = '{Currency}'
    """

    try:
        fetch_results = getattr(sf.bulk, "Account").query(query, lazy_operation=True)
        # Process and clean the results

        all_results = []
        for list_results in fetch_results:
            all_results.extend(list_results)

        def remove_attributes_keys(d):
            """
            Recursively remove keys that contain 'attributes_url' or 'attributes_type'.
            Also unpacks 'DNBConnect__D_B_Connect_Company_Profile__r' into its own columns.
            """
            if isinstance(d, dict):
                cleaned_dict = {}
                for k, v in d.items():
                    # Remove keys that contain 'attributes'
                    if "attributes" not in k:
                        if (
                            isinstance(v, dict)
                            and "DNBConnect__D_B_Connect_Company_Profile__r" in k
                        ):
                            # If value is a dict (nested), unpack its keys into the parent dictionary
                            for nested_k, nested_v in v.items():
                                cleaned_dict[nested_k] = nested_v
                        else:
                            # Otherwise, just add the key-value pair
                            cleaned_dict[k] = remove_attributes_keys(v)
                return cleaned_dict
            elif isinstance(d, list):
                return [remove_attributes_keys(i) for i in d]
            else:
                return d

        # Apply the cleaning function to the results
        cleaned_results = [remove_attributes_keys(result) for result in all_results]
        return cleaned_results
    except Exception as e:
        st.error(f"❌ Failed to fetch data: {str(e)}")
        return None


# Streamlit UI for fetching data
if "sf" in st.session_state:
    Currency = st.selectbox(
        "Select currency",
        [
            "USD",
            "EUR",
            "AUD",
            "GBP",
            "CAD",
            "CZK",
            "DKK",
            "HKD",
            "INR",
            "ILS",
            "MXN",
            "NZD",
            "NOK",
            "PLN",
            "RUB",
            "SGD",
            "ZAR",
            "LKR",
            "SEK",
            "CHF",
            "VND",
        ],
        key="CurrencyISO",
    )
    if st.button("🔍 Fetch Data"):
        results = fetch_and_clean_results(Currency)

        if results:
            # Convert to a Dataframe
            df = pd.DataFrame(results)
            # Remove unneeded columns
            df = df.drop(
                columns=["attributes", "DNBConnect__D_B_Connect_Company_Profile__r"]
            )
            Formatted_Salesforce_df = df[df["BillingStreet"].notnull()]
            Formatted_Salesforce_df = Formatted_Salesforce_df.drop(
                columns=[
                    "primAddr_streetAddr_line1__c",
                    "primAddr_AddrLocal_name__c",
                    "primAddr_Region_name__c",
                    "primAddr_postalCode__c",
                    "primAddr_Cntry_name__c",
                    "mailingAddr_streetAddr_line1__c",
                    "mailingAddr_AddrLocal_name__c",
                    "mailingAddr_Region_name__c",
                    "mailingAddr_postalCode__c",
                    "mailingAddr_Cntry_name__c",
                ]
            )
            filtered_rows_Primary = df[df["primAddr_streetAddr_line1__c"].notnull()]
            filtered_rows_Primary = filtered_rows_Primary.drop(
                columns=[
                    "BillingStreet",
                    "BillingCity",
                    "BillingState",
                    "BillingPostalCode",
                    "BillingCountry",
                    "mailingAddr_streetAddr_line1__c",
                    "mailingAddr_AddrLocal_name__c",
                    "mailingAddr_Region_name__c",
                    "mailingAddr_postalCode__c",
                    "mailingAddr_Cntry_name__c",
                ]
            )
            filtered_rows_Mailing = df[df["mailingAddr_streetAddr_line1__c"].notnull()]
            filtered_rows_Mailing = filtered_rows_Mailing.drop(
                columns=[
                    "BillingStreet",
                    "BillingCity",
                    "BillingState",
                    "BillingPostalCode",
                    "BillingCountry",
                    "primAddr_streetAddr_line1__c",
                    "primAddr_AddrLocal_name__c",
                    "primAddr_Region_name__c",
                    "primAddr_postalCode__c",
                    "primAddr_Cntry_name__c",
                ]
            )
            filtered_rows_Mailing.columns = Formatted_Salesforce_df.columns
            filtered_rows_Primary.columns = Formatted_Salesforce_df.columns
            st.session_state.salesforce_file = pd.concat(
                [Formatted_Salesforce_df, filtered_rows_Primary, filtered_rows_Mailing]
            )
            processed_Salesforce_path = os.path.join(
                TEMP_FOLDER, "processed_Salesforce.xlsx"
            )
            st.session_state.salesforce_file.to_excel(
                processed_Salesforce_path, index=False
            )
            st.success("✅ Salesforce data cleaned and stored!")
            st.download_button(
                label="📥 Download Processed Salesforce File",
                data=open(processed_Salesforce_path, "rb").read(),
                file_name=timestr + "processed_Salesforce.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                on_click="ignore",
            )

        else:
            st.error("❌ No data retrieved or an error occurred.")


if "sf" in st.session_state:  # Only show if user is logged in
    # Parameters for the function
    address_ratio_int = st.number_input(
        "📏 Address threshold", min_value=0, max_value=100, value=80
    )
    name_ratio_int = st.number_input(
        "🔠 Name threshold", min_value=0, max_value=100, value=80
    )

    RecordType = st.checkbox("Prospect Account Record Type?", key="RecordType")

    PaymentTerms = st.checkbox("Use Default Terms Net 30?", key="PaymentTerms")

    CurrencyISO = st.selectbox(
        "Select currency",
        [
            "USD",
            "EUR",
            "AUD",
            "GBP",
            "CAD",
            "CZK",
            "DKK",
            "HKD",
            "INR",
            "ILS",
            "MXN",
            "NZD",
            "NOK",
            "PLN",
            "RUB",
            "SGD",
            "ZAR",
            "LKR",
            "SEK",
            "CHF",
            "VND",
        ],
        key="CurrencyAccount",
    )

    def Compare(Acquisition_File, Salesforce_File, Address_Ratio_Int, Name_Ratio_Int):
        st.write("Starting Comparison")
        final_Colum = [
            "SF AccountID",
            "Legacy Customer ID",
            "Enterprise ID",
            "Account Name",
            "Full Address",
            "Billing City",
            "Billing State",
            "Postal Code",
            "Country",
            "Score",
        ]
        st.session_state.final = pd.DataFrame(columns=final_Colum)
        Copy_Formatted_Salesforce_df = Salesforce_File
        Acquisition_Data = Acquisition_File
        Enterprise_ID = len(Acquisition_Data["FullAddress"])
        # Initialize UI elements
        progress_bar = st.progress(0)
        status_text = st.empty()  # To display real-time status updates
        for index, column in enumerate(Acquisition_Data["FullAddress"]):
            progress = int((index + 1) / Enterprise_ID * 100)  # Calculate percentage
            progress_bar.progress(progress)  # Update progress bar
            status_text.text(
                f"📊 Progress: {index+1}/{Enterprise_ID}"
            )  # Show progress text
            for Salesforce_File_Index, Salesforce_File_Value in enumerate(
                Copy_Formatted_Salesforce_df["BillingStreet"]
            ):
                score = jellyfish.jaro_winkler_similarity(
                    (str(column).lower()), (str(Salesforce_File_Value).lower())
                )
                scorer = int(score * 100) >= int(Address_Ratio_Int)
                if scorer:
                    sName = str(
                        Copy_Formatted_Salesforce_df["Name"].iloc[
                            int(Salesforce_File_Index)
                        ]
                    )
                    aName = str(Acquisition_Data["Account Name"].iloc[int(index)])
                    nScore = jellyfish.jaro_winkler_similarity(
                        (sName.lower()), (aName.lower())
                    )
                    nScorer = int(nScore * 100) >= int(Name_Ratio_Int)
                    if nScorer:
                        st.session_state.final.loc[
                            len(st.session_state.final.index)
                        ] = [
                            "",
                            Acquisition_Data["Legacy Customer ID"]
                            .astype(str)
                            .iloc[int(index)],
                            "",
                            Acquisition_Data["Account Name"]
                            .astype(str)
                            .iloc[int(index)],
                            Acquisition_Data["FullAddress"]
                            .astype(str)
                            .iloc[int(index)],
                            Acquisition_Data["Billing City"]
                            .astype(str)
                            .iloc[int(index)],
                            Acquisition_Data["Billing State/Province"]
                            .astype(str)
                            .iloc[int(index)],
                            Acquisition_Data["Billing Zip/Postal Code"]
                            .astype(str)
                            .iloc[int(index)],
                            Acquisition_Data["Billing Country"]
                            .astype(str)
                            .iloc[int(index)],
                            "",
                        ]
                        st.session_state.final.loc[
                            len(st.session_state.final.index)
                        ] = [
                            Copy_Formatted_Salesforce_df["Id"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            "",
                            Copy_Formatted_Salesforce_df["Enterprise_ID__c"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            Copy_Formatted_Salesforce_df["Name"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            Copy_Formatted_Salesforce_df["BillingStreet"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            Copy_Formatted_Salesforce_df["BillingCity"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            Copy_Formatted_Salesforce_df["BillingState"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            Copy_Formatted_Salesforce_df["BillingPostalCode"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            Copy_Formatted_Salesforce_df["BillingCountry"]
                            .astype(str)
                            .iloc[int(Salesforce_File_Index)],
                            score,
                        ]
        processed_Compared_path = os.path.join(TEMP_FOLDER, "Matching_Accounts.xlsx")
        st.session_state.final.to_excel(processed_Compared_path, index=False)
        status_text.text("✅ Processing Complete!")
        st.success("All records processed successfully!")
        st.download_button(
            label="📥 Download Matching Accounts file ",
            data=open(processed_Compared_path, "rb").read(),
            file_name=timestr + "Matching_Accounts.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            on_click="ignore",
        )

    def Output(
        Acquisition_File,
        Currency,
        Term,
        pros,
    ):
        st.write("Building a File of De-Duplicated Accounts")
        outputs_colum = [
            "_Legacy Customer ID",
            "Name",
            "RecordTypeId",
            "Customer_Status__c",
            "Customer_Status_Assigned__c",
            "CurrencyIsoCode",
            "Payment_Terms__c",
            "Customer_Group__c",
            "Customer_Category__c",
            "WDIntegrate__c",
            "PublishToWorkday__c",
            "BillingStreet",
            "BillingCity",
            "BillingState",
            "BillingPostalCode",
            "BillingCountry",
            "Tax ID",
        ]
        outputs = pd.DataFrame(columns=outputs_colum)
        Found = st.session_state.final
        Copy_Acquisition_File = Acquisition_File
        if pros is True:
            Sf_Record_ID_Type = "012a00000018GZk"
            Workday = "n"
            Publish = "n"
            SF_Customer_Status = "Inactive"
            SF_Status = "Prospect"
        else:
            Sf_Record_ID_Type = "012a00000018GZgAAM"
            Workday = "y"
            Publish = "y"
            SF_Customer_Status = "Active"
            SF_Status = "Customer"
        for index, column in enumerate(Copy_Acquisition_File["Account Name"]):
            Index_Check = column in Found["Account Name"].values
            if Index_Check:
                continue
            else:
                payment_terms = (
                    Copy_Acquisition_File["Payment Terms"].astype(str).iloc[int(index)]
                    if Term is True
                    else "NET_30"
                )
                if str(column).startswith(
                    (
                        "A",
                        "B",
                        "C",
                        "D",
                        "E",
                        "F",
                        "G",
                        "H",
                        "I",
                        "J",
                        "K",
                        "L",
                        "M",
                        "a",
                        "b",
                        "c",
                        "d",
                        "e",
                        "f",
                        "g",
                        "h",
                        "i",
                        "j",
                        "k",
                        "l",
                        "m",
                        "1",
                        "2",
                        "3",
                        "4",
                        "5",
                        "6",
                        "7",
                        "8",
                        "9",
                        "0",
                        "(",
                        "Đ",
                        "Ô",
                    )
                ):
                    cgroup = "Statement_A-M"
                    outputs.loc[len(outputs.index)] = [
                        Copy_Acquisition_File["Legacy Customer ID"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Account Name"]
                        .str.title()
                        .iloc[int(index)],
                        Sf_Record_ID_Type,
                        SF_Customer_Status,
                        SF_Status,
                        Currency,
                        payment_terms,
                        cgroup,
                        "Trade",
                        Workday,
                        Publish,
                        Copy_Acquisition_File["FullAddress"]
                        .str.title()
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing City"]
                        .str.title()
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing State/Province"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing Zip/Postal Code"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing Country"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Tax ID"].astype(str).iloc[int(index)],
                    ]
                elif str(column).startswith(
                    (
                        "N",
                        "O",
                        "P",
                        "Q",
                        "R",
                        "S",
                        "T",
                        "U",
                        "V",
                        "W",
                        "X",
                        "Y",
                        "Z",
                        "n",
                        "o",
                        "p",
                        "q",
                        "r",
                        "s",
                        "t",
                        "u",
                        "v",
                        "w",
                        "x",
                        "y",
                        "z",
                    )
                ):
                    cgroup = "Statement_N-Z"
                    outputs.loc[len(outputs.index)] = [
                        Copy_Acquisition_File["Legacy Customer ID"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Account Name"]
                        .str.title()
                        .iloc[int(index)],
                        Sf_Record_ID_Type,
                        SF_Customer_Status,
                        SF_Status,
                        Currency,
                        payment_terms,
                        cgroup,
                        "Trade",
                        Workday,
                        Publish,
                        Copy_Acquisition_File["FullAddress"]
                        .str.title()
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing City"]
                        .str.title()
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing State/Province"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing Zip/Postal Code"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Billing Country"]
                        .astype(str)
                        .iloc[int(index)],
                        Copy_Acquisition_File["Tax ID"].astype(str).iloc[int(index)],
                    ]
        processed_dataload_path = os.path.join(
            TEMP_FOLDER, "New_Accounts_Dataload.xlsx"
        )
        outputs.to_excel(processed_dataload_path, index=False)
        st.success("File successfully Created!")
        st.download_button(
            label="📥 Download New Accounts Dataload file ",
            data=open(processed_dataload_path, "rb").read(),
            file_name=timestr + "New_Accounts_Dataload.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            on_click="ignore",
        )

    # Button to trigger the Clean_file function
    if st.button("🚀 Clean and Compare Files"):
        if acquisition_file and st.session_state.get("salesforce_file") is not None:
            # Read the uploaded and preprocessed files
            acquisition_df = pd.read_excel(processed_acquisition_path)

            # Retrieve the stored Salesforce file
            salesforce_df = st.session_state.salesforce_file

            Compare(
                acquisition_df,
                salesforce_df,
                address_ratio_int,
                name_ratio_int,
            )

            sleep(3)

            Output(acquisition_df, CurrencyISO, PaymentTerms, RecordType)
        else:
            st.warning("⚠️ Please provide Acquisition File.")
else:
    st.warning("⚠️ Please log in to access these features.")
