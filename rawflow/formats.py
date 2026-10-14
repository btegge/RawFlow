"""Candidate extensions are discovery hints, not claims of camera support."""
from pathlib import Path
RAW_EXTENSIONS = frozenset('.3fr .ari .arw .bay .cap .cr2 .cr3 .crw .dcr .dcs .dng .erf .fff .iiq .k25 .kdc .mdc .mef .mos .mrw .nef .nrw .orf .pef .ptx .raf .raw .rwl .rw2 .sr2 .srf .srw .x3f'.split())
RAW_TYPES = frozenset(x[1:].upper() for x in RAW_EXTENSIONS)


def is_raw_candidate(path):
    return Path(path).suffix.lower() in RAW_EXTENSIONS


def raw_patterns():
    return ' '.join('*'+ext for ext in sorted(RAW_EXTENSIONS))+' '+ ' '.join('*'+ext.upper() for ext in sorted(RAW_EXTENSIONS))
