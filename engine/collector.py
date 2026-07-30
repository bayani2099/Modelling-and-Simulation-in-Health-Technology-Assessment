import pandas as pd
from .agents import SUSCEPTIBLE, EXPOSED, INFECTIOUS, RECOVERED


class TimeSeriesCollector:
    def __init__(self):
        self.rows = []

    def collect(self, model):
        def count(group, state):
            return sum(1 for a in group if a.state == state)

        row = {
            "t": model.time,
            "week": model.week_float(model.time),
            "p_ext": model.external_pressure(model.time),

            # SEIR by group
            "S_pupils": count(model.pupils, SUSCEPTIBLE),
            "E_pupils": count(model.pupils, EXPOSED),
            "I_pupils": count(model.pupils, INFECTIOUS),
            "R_pupils": count(model.pupils, RECOVERED),

            "S_teachers": count(model.teachers, SUSCEPTIBLE),
            "E_teachers": count(model.teachers, EXPOSED),
            "I_teachers": count(model.teachers, INFECTIOUS),
            "R_teachers": count(model.teachers, RECOVERED),

            "S_staff": count(model.staff, SUSCEPTIBLE),
            "E_staff": count(model.staff, EXPOSED),
            "I_staff": count(model.staff, INFECTIOUS),
            "R_staff": count(model.staff, RECOVERED),

            # isolation
            "isolated_pupils": sum(1 for a in model.pupils if a.isolated),
            "isolated_teachers": sum(1 for a in model.teachers if a.isolated),
            "isolated_staff": sum(1 for a in model.staff if a.isolated),

            # per-step counters
            "new_infections_internal": model.new_infections_internal,
            "new_infections_external": model.new_infections_external,
            "tests_administered": model.tests_administered,
        }

        self.rows.append(row)

    def to_df(self):
        return pd.DataFrame(self.rows)
