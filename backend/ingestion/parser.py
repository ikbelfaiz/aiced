"""Bounded OOXML parsing. Never evaluates formulas or attempts identity inference."""

from collections import Counter
import math
from datetime import date, datetime
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from xml.etree.ElementTree import ParseError
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework.exceptions import ValidationError
from .templates import TEMPLATES

MAX_BYTES = 10 * 1024 * 1024
MAX_EXPANDED = 25 * 1024 * 1024
MAX_ROWS = 50000


def fail(message):
    raise ValidationError(message)


def parse(content, template, date_format="ISO"):
    spec = TEMPLATES[template]
    if date_format not in ["ISO", "DMY"]:
        fail("Format de date non pris en charge.")
    if not content or len(content) > MAX_BYTES:
        fail("Fichier vide ou supérieur à 10 Mio.")
    if not content.startswith(b"PK\x03\x04"):
        fail("Classeur invalide : signature ZIP/XLSX attendue.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 1000 or len(names) != len(set(names)):
                fail("Archive excessive ou entrées dupliquées.")
            if sum(entry.file_size for entry in entries) > MAX_EXPANDED:
                fail("Archive décompressée supérieure à 25 Mio.")
            for entry in entries:
                name = entry.filename.lower()
                if (
                    ".." in name.split("/")
                    or name.startswith(("/", "\\"))
                    or "\\" in name
                ):
                    fail("Chemin ZIP interdit.")
                if (
                    entry.flag_bits & 1
                    or entry.file_size > MAX_EXPANDED
                    or entry.file_size > max(1, entry.compress_size) * 200
                ):
                    fail("Archive chiffrée ou compression excessive.")
                if any(
                    part in name
                    for part in [
                        "vbaproject",
                        "externallinks/",
                        "embeddings/",
                        "activex/",
                    ]
                ):
                    fail("Macros, objets ou liens externes interdits.")
                if name.endswith((".xml", ".rels")):
                    root = fromstring(archive.read(entry))
                    for element in root.iter():
                        if (
                            "macroenabled"
                            in element.attrib.get("ContentType", "").lower()
                        ):
                            fail("Contenu macro interdit.")
                        if element.attrib.get("TargetMode", "").lower() == "external":
                            fail("Liens externes interdits.")
                        if element.tag.endswith("}c") and name.startswith(
                            "xl/worksheets/"
                        ):
                            ref = element.attrib.get("r", "")
                            letters = "".join(c for c in ref if c.isalpha())
                            if letters and openpyxl.utils.column_index_from_string(
                                letters
                            ) > len(spec["headers"]):
                                fail("Colonnes hors schéma.")
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                fail("Classeur XLSX attendu.")
        workbook = openpyxl.load_workbook(
            BytesIO(content), read_only=True, data_only=False, keep_links=False
        )
        try:
            if workbook.sheetnames != [spec["sheet"]]:
                fail("Une seule feuille attendue : " + spec["sheet"])
            sheet = workbook.active
            sheet.reset_dimensions()
            iterator = sheet.iter_rows(max_col=len(spec["headers"]))
            header = next(iterator, None)
            actual = [cell.value for cell in header] if header else []
            if actual != spec["headers"]:
                fail("En-têtes ou positions différents du modèle versionné.")
            rows = []
            for number, cells in enumerate(iterator, 2):
                if number > MAX_ROWS + 1:
                    fail("Limite de 50 000 lignes dépassée.")
                if all(cell.value is None for cell in cells):
                    continue
                errors = []
                normalized_dates = {}
                values = {}
                for position, cell in enumerate(cells, 1):
                    value = cell.value
                    if isinstance(value,float) and not math.isfinite(value):
                        errors.append(f'colonne {position} : nombre non fini interdit')
                        value=str(value)
                    if cell.data_type in ["f", "e"]:
                        errors.append(
                            f"colonne {position} : formule ou erreur Excel interdite"
                        )
                    if isinstance(value, (datetime, date)):
                        value = value.isoformat()
                    if value is not None and not isinstance(
                        value, (str, int, float, bool)
                    ):
                        errors.append(f"colonne {position} : type non pris en charge")
                        value = str(value)
                    if isinstance(value, str) and len(value) > 2000:
                        errors.append(
                            f"colonne {position} : texte supérieur à 2 000 caractères"
                        )
                    values[str(position)] = value
                    label = spec["headers"][position - 1] or ""
                    if value not in (None, "") and label in [
                        "Date de naissance",
                        "Date d'ouverture",
                        "Creation Date",
                        "Update Date",
                    ]:
                        try:
                            if (
                                isinstance(cell.value, (date, datetime))
                                or date_format == "ISO"
                            ):
                                parsed_value = datetime.fromisoformat(str(value))
                            else:
                                if len(str(value)) not in [10, 19]:
                                    raise ValueError()
                                parsed_value = datetime.strptime(
                                    str(value),
                                    (
                                        "%d/%m/%Y %H:%M:%S"
                                        if len(str(value)) == 19
                                        else "%d/%m/%Y"
                                    ),
                                )
                            parsed = parsed_value.date()
                            if "naissance" in label and parsed > date.today():
                                raise ValueError()
                            normalized_dates[str(position)] = (
                                parsed_value.isoformat()
                                if " " in str(value) or "T" in str(value)
                                else parsed.isoformat()
                            )
                        except ValueError:
                            errors.append(
                                f"colonne {position} : date {date_format} ou date Excel attendue"
                            )
                keys = [values[str(p)] for p in spec["candidate_keys"]]
                if not any(isinstance(key, str) and key.strip() for key in keys):
                    errors.append(
                        "Identifiant texte manquant ; aucune conversion numérique implicite"
                    )
                for key in keys:
                    if key not in (None, "") and (
                        not isinstance(key, str) or len(key) > 160 or key != key.strip()
                    ):
                        errors.append(
                            "Identifiant ambigu, numérique, espacé ou trop long"
                        )
                rows.append(
                    {
                        "number": number,
                        "cells": values,
                        "errors": errors,
                        "warnings": [],
                        "normalized_dates": normalized_dates,
                    }
                )
            if not rows:
                fail("Classeur sans ligne de données.")
            for position in spec["candidate_keys"]:
                counts = Counter(
                    row["cells"][str(position)]
                    for row in rows
                    if isinstance(row["cells"][str(position)], str)
                    and row["cells"][str(position)]
                )
                for row in rows:
                    if counts.get(row["cells"][str(position)], 0) > 1:
                        row["errors"].append(f"Doublon colonne {position} dans le lot")
            return rows
        finally:
            workbook.close()
    except (
        BadZipFile,
        DefusedXmlException,
        ParseError,
        InvalidFileException,
        KeyError,
        ValueError,
        TypeError,
        IndexError,
        StopIteration,
        OSError,
        EOFError,
        NotImplementedError,
    ):
        fail("Classeur OOXML invalide ou dangereux.")
