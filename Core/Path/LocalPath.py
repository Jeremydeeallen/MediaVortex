import os


# directive: path-schema-migration | # see path.S3
def LocalBasename(Value):
    return os.path.basename(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalDirname(Value):
    return os.path.dirname(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalSplitExt(Value):
    return os.path.splitext(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalJoin(Base, *Children):
    Cleaned = [str(C) for C in Children if C is not None and C != ""]
    return os.path.join(Base or "", *Cleaned)


# directive: path-schema-migration | # see path.S3
def LocalExists(Value):
    return bool(Value) and os.path.exists(Value)


# directive: path-schema-migration | # see path.S3
def LocalIsFile(Value):
    return bool(Value) and os.path.isfile(Value)


# directive: path-schema-migration | # see path.S3
def LocalIsDir(Value):
    return bool(Value) and os.path.isdir(Value)


# directive: path-schema-migration | # see path.S3
def LocalGetSize(Value):
    return os.path.getsize(Value)


# directive: path-schema-migration | # see path.S3
def LocalGetMTime(Value):
    return os.path.getmtime(Value)


# directive: path-schema-migration | # see path.S3
def LocalNormCase(Value):
    return os.path.normcase(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalSamePath(A, B):
    return os.path.normcase(A or "") == os.path.normcase(B or "")
