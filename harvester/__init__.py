"""INTERPLANT harvester: parse ARCs and upsert L2 records into Postgres.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
# arctrl API used (verified Task 2): arctrl.ARC.load(path) -> ARC
# Fields: arc.Title / .Identifier / .Description / .Studies[i].Identifier
#         / .Assays (top-level, not nested under Studies) / .Contacts
