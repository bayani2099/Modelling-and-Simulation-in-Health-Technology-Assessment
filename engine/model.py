import random
from mesa import Model

from .agents import Pupil, Teacher, Staff, INFECTIOUS
from .collector import TimeSeriesCollector
from .scenario import Scenario

class RandomScheduler:
    def __init__(self, rng: random.Random):
        self.agents = []
        self.rng = rng

    def add(self, agent):
        self.agents.append(agent)

    def step(self):
        self.rng.shuffle(self.agents)
        for agent in self.agents:
            agent.step()

class SchoolModel(Model):
    def __init__(self, scenario: Scenario, seed: int | None = None):
        super().__init__()
        self.scenario = scenario
        self.rng = random.Random(seed)

        self.school_hours_per_day = scenario.school_hours_per_day
        self.latent_period = scenario.latent_period
        self.infectious_period = scenario.infectious_period
        self.isolation_duration = scenario.isolation_days * self.school_hours_per_day

        self.base_beta = scenario.base_beta
        self.test_sensitivity = scenario.test_sensitivity
        self.testing_interval_hours = scenario.testing_interval_hours

        self.mental_health_penalty_isolation = scenario.mental_health_penalty_isolation
        self.mental_health_penalty_per_test = scenario.mental_health_penalty_per_test

        self.contact_multipliers = scenario.contact_multipliers
        self.out_of_class_contact_rate = scenario.out_of_class_contact_rate

        self.time = 0
        self.schedule = RandomScheduler(self.rng)
        self.collector = TimeSeriesCollector()

        self.classrooms: dict[str, list[Pupil]] = {}
        self.pupils: list[Pupil] = []
        self.teachers: list[Teacher] = []
        self.staff: list[Staff] = []

        # per-step counters
        self.new_infections_internal = 0
        self.new_infections_external = 0
        self.tests_administered = 0

        self.create_school()
        self.rng.choice(self.schedule.agents).state = INFECTIOUS
        self.collector.collect(self)

    def create_school(self):
        for grade in range(self.scenario.num_grades):
            for c in range(self.scenario.classes_per_grade):
                class_id = f"G{grade}_C{c}"
                self.classrooms[class_id] = []

                for _ in range(self.scenario.pupils_per_class):
                    v = self.rng.random() < self.scenario.pupil_vaccination_rate
                    p = Pupil(self, class_id, grade, v)
                    self.schedule.add(p)
                    self.classrooms[class_id].append(p)
                    self.pupils.append(p)

                v = self.rng.random() < self.scenario.teacher_vaccination_rate
                t = Teacher(self, [class_id], v)
                self.schedule.add(t)
                self.teachers.append(t)

        for _ in range(self.scenario.num_staff):
            v = self.rng.random() < self.scenario.staff_vaccination_rate
            s = Staff(self, v)
            self.schedule.add(s)
            self.staff.append(s)

    def step(self):
        self.new_infections_internal = 0
        self.new_infections_external = 0
        self.tests_administered = 0

        self.apply_external_infection()
        self.perform_testing()
        self.schedule.step()

        self.time += 1
        self.collector.collect(self)

    def random_pupil_same_grade(self, grade: int, exclude: Pupil):
        candidates = [p for p in self.pupils if p.grade == grade and p is not exclude]
        if not candidates:
            return None
        return self.rng.choice(candidates)

    # ----- dynamic external force -----
    def week_float(self, t: int) -> float:
        return t / (self.school_hours_per_day * 5)

    def external_pressure(self, t: int) -> float:
        points = self.scenario.ext_force_points
        mode = self.scenario.ext_force_mode
        w = self.week_float(t)

        if w <= points[0][0]:
            return float(points[0][1])
        if w >= points[-1][0]:
            return float(points[-1][1])

        for i in range(len(points) - 1):
            w0, p0 = points[i]
            w1, p1 = points[i + 1]
            if w0 <= w <= w1:
                if mode == "step":
                    return float(p0)
                alpha = (w - w0) / (w1 - w0) if (w1 - w0) != 0 else 0.0
                return float(p0 + alpha * (p1 - p0))

        return float(points[-1][1])

    def apply_external_infection(self):
        p_ext = self.external_pressure(self.time)
        for a in self.schedule.agents:
            if a.susceptible and self.rng.random() < p_ext:
                a.expose(source="external")

    def perform_testing(self):
        interval = self.testing_interval_hours
        if interval is None or self.time % interval != 0:
            return

        for a in self.schedule.agents:
            self.tests_administered += 1
            a.mental_health_score -= self.mental_health_penalty_per_test

            if a.infectious and not a.isolated:
                if self.rng.random() < self.test_sensitivity:
                    a.isolated = True
                    a.isolation_timer = self.isolation_duration

    def transmission_probability(self, contact_type: str, a, b) -> float:
        p = self.base_beta * float(self.contact_multipliers[contact_type])

        if getattr(a, "vaccinated", False):
            p *= (1 - self.scenario.vaccine_infectiousness_reduction)
        if getattr(b, "vaccinated", False):
            p *= (1 - self.scenario.vaccine_susceptibility_reduction)

        return p
