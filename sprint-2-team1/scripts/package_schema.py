FIELDS = [
    "specialty_code",
    "specialty_name",
    "package_code",
    "package_name",
    "procedure_code",
    "procedure_name",
    "tier3_price",
    "tier2_price",
    "tier1_price",
    "stratification_remarks",
    "implant_mapped",
    "implant_cost",
    "source_page",
]

SOURCE_COLUMN_INDEX = {
    "specialty_code": 1,
    "specialty_name": 0,
    "package_code": 2,
    "package_name": 3,
    "procedure_code": 4,
    "procedure_name": 5,
    "tier3_price": 6,
    "tier2_price": 7,
    "tier1_price": 8,
    "implant_mapped": 9,
    "implant_cost": 10,
    "stratification_remarks": 11,
}

PRICE_FIELDS = {"tier3_price", "tier2_price", "tier1_price", "implant_cost"}
REQUIRED_TEXT_FIELDS = {
    "specialty_code",
    "specialty_name",
    "package_code",
    "package_name",
    "procedure_code",
    "procedure_name",
    "stratification_remarks",
}
