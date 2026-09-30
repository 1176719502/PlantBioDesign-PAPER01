"""
core/part_library.py

Core domain model for the BioDesign Studio part library.
Handles BioPart data definitions and SQLite-backed persistence.
No external dependencies — stdlib only.
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Core registry types (used by the Parts Registry / database layer)
VALID_PART_TYPES = {"promoter", "RBS", "CDS", "terminator", "vector"}

# Extended set accepted by BioPart dataclass.  Includes all types that the
# Expression Wizard frame-builder can produce (e.g. "Kozak" for eukaryotic
# hosts, "misc" / "other" as a safe fallback) without crashing Step 4.
_BIOPART_VALID_TYPES = VALID_PART_TYPES | {"Kozak", "misc", "other"}


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class BioPart:
    """Represents a single biological part (genetic element)."""

    name: str
    part_type: str
    sequence: str
    description: str = ""
    part_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        """Validate fields immediately after construction."""
        self._validate_part_type()
        self._validate_sequence()

    # ---- validators --------------------------------------------------------

    def _validate_part_type(self) -> None:
        """Ensure part_type is one of the accepted categories.

        The Wizard frame-builder can produce types beyond the core registry
        set (e.g. 'Kozak' for eukaryotic RBS elements, 'misc'/'other' as a
        safe fallback).  These are accepted here so that Step 4 primer design
        never crashes on a valid Wizard-generated part.  The stricter
        VALID_PART_TYPES set is still used by the Parts Registry / database
        layer.
        """
        if self.part_type not in _BIOPART_VALID_TYPES:
            # Coerce unknown types to 'other' rather than raising, so that
            # novel host-specific part types never block the Wizard path.
            self.part_type = "other"

    def _validate_sequence(self) -> None:
        """Ensure sequence contains only A, T, C, G, N characters.

        N is accepted because the Parts Registry allows it (IUPAC ambiguity
        base), and some Wizard-generated regulatory elements (e.g. promoter
        sequences pulled from the DB) may legitimately contain N.
        Hard invalid characters (non-IUPAC letters, digits, whitespace) still
        raise ValueError so truly bad input is caught early.
        """
        cleaned = self.sequence.upper()
        invalid = set(cleaned) - {"A", "T", "C", "G", "N"}
        if invalid:
            raise ValueError(
                f"Sequence contains invalid characters: {invalid}. "
                "Only A, T, C, G, N are allowed."
            )
        # Normalize to uppercase for consistency
        self.sequence = cleaned


# ---------------------------------------------------------------------------
# Database Manager
# ---------------------------------------------------------------------------

class PartLibraryManager:
    """
    Manages CRUD operations for BioPart objects stored in a local SQLite
    database.  All public methods return plain Python objects — no Streamlit
    or UI logic here.
    """

    # SQL statements kept as class-level constants for readability
    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS parts (
            part_id    TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            part_type  TEXT NOT NULL,
            sequence   TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
    """

    _INSERT_SQL = """
        INSERT INTO parts (part_id, name, part_type, sequence, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?);
    """

    _SELECT_BY_ID_SQL = """
        SELECT part_id, name, part_type, sequence, description, created_at
        FROM parts
        WHERE part_id = ?;
    """

    _DELETE_SQL = "DELETE FROM parts WHERE part_id = ?;"

    # -----------------------------------------------------------------------

    def __init__(self, db_path: str = "data/bio_db.sqlite") -> None:
        """
        Connect to (or create) the SQLite database and ensure the
        'parts' table exists.

        Args:
            db_path: Relative or absolute path to the .sqlite file.
                     The parent directory must already exist.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection = sqlite3.connect(
            db_path,
            check_same_thread=False,   # safe for single-threaded Streamlit
        )
        self._conn.row_factory = sqlite3.Row  # column access by name
        self._ensure_table()

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """Create the parts table if it does not exist yet."""
        with self._conn:
            self._conn.execute(self._CREATE_TABLE_SQL)

    @staticmethod
    def _row_to_biopart(row: sqlite3.Row) -> BioPart:
        """Convert a database row into a BioPart instance."""
        return BioPart(
            part_id=row["part_id"],
            name=row["name"],
            part_type=row["part_type"],
            sequence=row["sequence"],
            description=row["description"],
            created_at=row["created_at"],
        )

    # -----------------------------------------------------------------------
    # Public CRUD API
    # -----------------------------------------------------------------------

    def add_part(self, part: BioPart) -> str:
        """
        Persist a BioPart to the database.

        Args:
            part: A validated BioPart instance.

        Returns:
            The part_id string of the newly stored record.

        Raises:
            ValueError: If a part with the same part_id already exists.
            sqlite3.Error: On any underlying database error.
        """
        try:
            with self._conn:
                self._conn.execute(
                    self._INSERT_SQL,
                    (
                        part.part_id,
                        part.name,
                        part.part_type,
                        part.sequence,
                        part.description,
                        part.created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A part with part_id '{part.part_id}' already exists."
            ) from exc

        return part.part_id

    def get_part(self, part_id: str) -> Optional[BioPart]:
        """
        Retrieve a single BioPart by its ID.

        Args:
            part_id: UUID string of the desired part.

        Returns:
            A BioPart instance, or None if not found.
        """
        cursor = self._conn.execute(self._SELECT_BY_ID_SQL, (part_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_biopart(row)

    def search_parts(
        self,
        part_type: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> list:
        """
        Search the parts library with optional filters.

        Args:
            part_type: If provided, restrict results to this part type.
            keyword:   If provided, filter by case-insensitive substring
                       match on the part name or description.

        Returns:
            A list of matching BioPart objects (may be empty).
        """
        # Build query dynamically based on which filters were supplied
        conditions: list = []
        params: list = []

        if part_type is not None:
            if part_type not in VALID_PART_TYPES:
                raise ValueError(
                    f"Invalid part_type filter '{part_type}'. "
                    f"Must be one of: {sorted(VALID_PART_TYPES)}"
                )
            conditions.append("part_type = ?")
            params.append(part_type)

        if keyword is not None:
            # Search in both name and description
            conditions.append("(name LIKE ? OR description LIKE ?)")
            like_token = f"%{keyword}%"
            params.extend([like_token, like_token])

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT part_id, name, part_type, sequence, description, created_at
            FROM parts
            {where_clause}
            ORDER BY created_at DESC;
        """

        cursor = self._conn.execute(sql, params)
        return [self._row_to_biopart(row) for row in cursor.fetchall()]

    def delete_part(self, part_id: str) -> bool:
        """
        Remove a part from the database by its ID.

        Args:
            part_id: UUID string of the part to delete.

        Returns:
            True if a record was deleted, False if no matching ID was found.
        """
        with self._conn:
            cursor = self._conn.execute(self._DELETE_SQL, (part_id,))
        return cursor.rowcount > 0

    # -----------------------------------------------------------------------
    # FASTA Parsing
    # -----------------------------------------------------------------------

    # Full IUPAC nucleotide alphabet used for sequence validation
    _VALID_BASES: frozenset = frozenset("ATCGNRYSWKMBDHVU")

    @staticmethod
    def parse_fasta(fasta_text: str) -> list:
        """
        Parse a string in standard FASTA format into a list of dicts.

        Each record in the returned list has the form::

            {"name": "sequence_identifier", "sequence": "ATCGATCG..."}

        Parsing rules
        -------------
        * Lines starting with ``>`` begin a new record.  The identifier is
          the first whitespace-delimited token after ``>``; any additional
          description text on the same header line is silently ignored.
        * All non-header lines between two header lines (or between the last
          header and EOF) are concatenated; every whitespace character
          (space, tab, CR, LF) is stripped to form the final sequence string.
        * Records whose header is present but sequence is empty are skipped.
        * The assembled sequence is validated against the full IUPAC
          nucleotide alphabet (``ATCGNRYSWKMBDHVU``, case-insensitive).
          A ``ValueError`` is raised if any invalid character is detected.

        Args:
            fasta_text: Raw FASTA-formatted text; multi-record input is
                        supported.

        Returns:
            A list of dicts, e.g.
            ``[{"name": "seq1", "sequence": "ATCGATCG..."}, ...]``.

        Raises:
            ValueError: If no valid FASTA records are found, or if a
                        sequence contains characters outside the IUPAC
                        nucleotide alphabet.
        """
        valid_bases: frozenset = frozenset("ATCGNRYSWKMBDHVU")
        records: list = []
        current_name: Optional[str] = None
        sequence_lines: list = []

        def _flush(name: Optional[str], lines: list) -> None:
            """Assemble, validate, and append the accumulated record."""
            if name is None:
                return
            # Concatenate all lines then remove every whitespace character
            sequence = "".join("".join(lines).split())
            if not sequence:
                return  # header-only record with no sequence data — skip
            upper_seq = sequence.upper()
            invalid_chars = set(upper_seq) - valid_bases
            if invalid_chars:
                raise ValueError(
                    f"FASTA record '{name}' contains invalid nucleotide "
                    f"character(s): {sorted(invalid_chars)}. "
                    "Expected IUPAC nucleotide alphabet "
                    "(A, T, C, G, N, R, Y, S, W, K, M, B, D, H, V, U)."
                )
            records.append({"name": name, "sequence": upper_seq})

        for line in fasta_text.splitlines():
            stripped = line.strip()
            if not stripped:            # skip blank / whitespace-only lines
                continue
            if stripped.startswith(">"):
                _flush(current_name, sequence_lines)  # save the previous record
                header = stripped[1:].strip()
                # Identifier = first whitespace-delimited token after '>'
                current_name = header.split()[0] if header else ""
                sequence_lines = []
            else:
                sequence_lines.append(stripped)

        _flush(current_name, sequence_lines)  # flush the final record

        if not records:
            raise ValueError(
                "No valid FASTA records found in the provided text. "
                "Ensure the input contains at least one header line "
                "starting with '>' followed by non-empty sequence data."
            )

        return records

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def close(self) -> None:
        """Explicitly close the database connection."""
        self._conn.close()

    def __del__(self) -> None:
        """Ensure the connection is closed when the manager is garbage-collected."""
        try:
            self._conn.close()
        except Exception:
            pass
