from dataclasses import dataclass

@dataclass
class Scenario:
    name: str = "daily_testing"

    classes_per_grade: int = 5
    pupils_per_class: int = 22
    num_grades: int = 4
    num_staff: int = 10

    latent_period: int = 24
    infectious_period: int = 72

    school_hours_per_day: int = 8
    isolation_days: int = 5

    test_sensitivity: float = 0.8
    testing_interval_hours: int | None = 8

    base_beta: float = 0.02
    contact_multipliers: dict | None = None

    pupil_vaccination_rate: float = 0.2
    teacher_vaccination_rate: float = 0.8
    staff_vaccination_rate: float = 0.8
    vaccine_susceptibility_reduction: float = 0.7
    vaccine_infectiousness_reduction: float = 0.5

    mental_health_penalty_isolation: float = 0.1
    mental_health_penalty_per_test: float = 0.01

    ext_force_points: list | None = None
    ext_force_mode: str = "linear"

    out_of_class_contact_rate: float = 0.02

    # GUI defaults
    weeks: int = 8
    n_runs: int = 100
    base_seed: int = 1234

    def __post_init__(self):
        if self.contact_multipliers is None:
            self.contact_multipliers = {
                "pupil_pupil": 1.0,
                "teacher_pupil": 0.8,
                "teacher_teacher": 1.2,
                "teacher_staff": 1.0,
                "staff_staff": 0.5,
            }

        if self.ext_force_points is None:
            self.ext_force_points = [
                (0, 1e-5),
                (3, 1e-5),
                (4, 5e-5),
                (7, 5e-5),
                (8, 1e-5),
            ]
