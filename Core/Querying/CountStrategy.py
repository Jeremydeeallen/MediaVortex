from enum import Enum


# directive: paged-query-core | # see paged-query.C10
class CountStrategy(Enum):
    WINDOW = "window"
    SEPARATE = "separate"
    NONE = "none"
