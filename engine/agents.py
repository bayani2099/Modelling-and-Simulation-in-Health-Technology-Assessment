from mesa import Agent

SUSCEPTIBLE = "S"
EXPOSED = "E"
INFECTIOUS = "I"
RECOVERED = "R"

class BasePerson(Agent):
    def __init__(self, model, vaccinated=False):
        super().__init__(model)
        self.vaccinated = vaccinated
        self.state = SUSCEPTIBLE
        self.time_since_infection = 0
        self.isolated = False
        self.isolation_timer = 0

        # outcomes
        self.missed_school_days = 0.0
        self.mental_health_score = 0.0

    @property
    def susceptible(self):
        return self.state == SUSCEPTIBLE

    @property
    def infectious(self):
        return self.state == INFECTIOUS

    def expose(self, source="internal"):
        """
        source: "internal" or "external"
        We increment model counters here so they are correct regardless of who infects whom.
        """
        if self.state != SUSCEPTIBLE:
            return

        self.state = EXPOSED
        self.time_since_infection = 0

        if source == "external":
            self.model.new_infections_external += 1
        else:
            self.model.new_infections_internal += 1

    def progress_disease(self):
        if self.state in (EXPOSED, INFECTIOUS):
            self.time_since_infection += 1

        if self.state == EXPOSED and self.time_since_infection >= self.model.latent_period:
            self.state = INFECTIOUS

        if self.state == INFECTIOUS and self.time_since_infection >= self.model.infectious_period:
            self.state = RECOVERED

    def step(self):
        if self.isolated:
            self.isolation_timer -= 1
            if self.isolation_timer <= 0:
                self.isolated = False
            return
        self.progress_disease()


class Pupil(BasePerson):
    def __init__(self, model, class_id, grade, vaccinated):
        super().__init__(model, vaccinated)
        self.class_id = class_id
        self.grade = grade

    def step(self):
        if self.isolated:
            self.missed_school_days += 1 / self.model.school_hours_per_day
            self.mental_health_score -= self.model.mental_health_penalty_isolation
            super().step()
            return

        super().step()
        self.interact()

    def interact(self):
        # In-class: contact all classmates (simple baseline)
        classmates = self.model.classrooms[self.class_id]
        for other in classmates:
            if other is not self and not other.isolated:
                self.try_transmit(other, "pupil_pupil")

        # Out-of-class: random same-grade mixing at low rate
        if self.model.out_of_class_contact_rate > 0:
            if self.model.rng.random() < self.model.out_of_class_contact_rate:
                other = self.model.random_pupil_same_grade(self.grade, exclude=self)
                if other is not None and not other.isolated:
                    self.try_transmit(other, "pupil_pupil")

    def try_transmit(self, other, contact_type):
        if not self.infectious or not other.susceptible:
            return

        p = self.model.transmission_probability(contact_type, self, other)
        if self.model.rng.random() < p:
            other.expose(source="internal")


class Teacher(BasePerson):
    def __init__(self, model, classes, vaccinated):
        super().__init__(model, vaccinated)
        self.classes = classes

    def step(self):
        if self.isolated:
            super().step()
            return

        super().step()
        self.interact()

    def interact(self):
        # teacher-teacher
        for other in self.model.teachers:
            if other is not self and not other.isolated:
                self.try_transmit(other, "teacher_teacher")

        # teacher-pupil
        for class_id in self.classes:
            for pupil in self.model.classrooms[class_id]:
                if not pupil.isolated:
                    self.try_transmit(pupil, "teacher_pupil")

        # teacher-staff (optional)
        for staff in self.model.staff:
            if not staff.isolated:
                self.try_transmit(staff, "teacher_staff")

    def try_transmit(self, other, contact_type):
        if not self.infectious or not other.susceptible:
            return

        p = self.model.transmission_probability(contact_type, self, other)
        if self.model.rng.random() < p:
            other.expose(source="internal")


class Staff(BasePerson):
    def __init__(self, model, vaccinated):
        super().__init__(model, vaccinated)

    def step(self):
        if self.isolated:
            super().step()
            return

        super().step()

        # staff-staff (low)
        for other in self.model.staff:
            if other is not self and not other.isolated:
                self.try_transmit(other, "staff_staff")

    def try_transmit(self, other, contact_type):
        if not self.infectious or not other.susceptible:
            return

        p = self.model.transmission_probability(contact_type, self, other)
        if self.model.rng.random() < p:
            other.expose(source="internal")
