"""Guided lessons ("úkoly") chosen by what is visible right now."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from obloha.beginner.describe import (
    direction_arrow,
    direction_name,
    direction_word,
    fist_text,
    height_word,
    position_sentence,
)
from obloha.core.sky import ObjectRef, SkyScene, limiting_magnitude_for_sun

Guide = tuple[ObjectRef, ObjectRef]


@dataclass(frozen=True)
class LessonView:
    """What the UI shows for a lesson at a given hint level."""

    steps: tuple[str, ...]
    highlights: tuple[ObjectRef, ...] = ()
    guides: tuple[Guide, ...] = ()
    labels: frozenset[ObjectRef] = frozenset()
    hint_circle: tuple[float, float, float] | None = None
    look_az: float = 180.0
    look_alt: float = 30.0
    asterism: str | None = None


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    available: Callable[[SkyScene], bool]
    build: Callable[[SkyScene, int], LessonView]
    tags: tuple[str, ...] = field(default_factory=tuple)


def _star(scene: SkyScene, name: str) -> ObjectRef:
    i = scene.cat.star_by_key(name)
    assert i is not None, name
    return ObjectRef.star(i)


def _alt(scene: SkyScene, ref: ObjectRef) -> float:
    pos = scene.altaz_of(ref)
    return pos[0] if pos else -90.0


def _pos(scene: SkyScene, ref: ObjectRef) -> tuple[float, float]:
    pos = scene.altaz_of(ref)
    assert pos is not None
    return pos


def _dark_enough(scene: SkyScene, mag: float = 2.0) -> bool:
    return limiting_magnitude_for_sun(scene.sun_alt, 6.0) >= mag


def _look(scene: SkyScene, refs: list[ObjectRef]) -> tuple[float, float]:
    """Viewing direction that frames all ``refs`` (average azimuth, lowest altitude)."""
    import math

    pts = [_pos(scene, r) for r in refs]
    x = sum(math.cos(math.radians(az)) for _, az in pts)
    y = sum(math.sin(math.radians(az)) for _, az in pts)
    az = math.degrees(math.atan2(y, x)) % 360
    return az, min(alt for alt, _ in pts)


def _finish(
    scene: SkyScene,
    steps: list[str],
    targets: list[ObjectRef],
    guides: list[Guide],
    level: int,
    asterism: str | None = None,
    focus: ObjectRef | None = None,
) -> LessonView:
    focus = focus or targets[0]
    look_az, look_alt = _look(scene, targets)
    circle = None
    highlights: tuple[ObjectRef, ...] = ()
    if level >= 1:
        alt, az = _pos(scene, focus)
        circle = (alt, az, 12.0 if level == 1 else 6.0)
    if level >= 2:
        highlights = tuple(targets)
        if asterism:
            highlights += (ObjectRef("asterism", asterism),)
    hint_steps = list(steps)
    if level >= 1:
        alt, az = _pos(scene, focus)
        hint_steps.append(
            f"Nápověda: hledej {height_word(alt)} {direction_word(az)}, {fist_text(alt)} "
            "nad obzorem. Oblast je zvýrazněná v mapě."
        )
    return LessonView(
        steps=tuple(hint_steps),
        highlights=highlights,
        guides=tuple(guides),
        labels=frozenset(targets),
        hint_circle=circle,
        look_az=look_az,
        look_alt=look_alt,
        asterism=asterism,
    )


# ---------------------------------------------------------------- lessons
def _brightest_planet(scene: SkyScene) -> ObjectRef | None:
    cands = [
        b
        for b in scene.bodies.values()
        if b.info.kind == "planet" and b.alt > 5 and b.mag < 2.0 and b.elongation > 10
    ]
    if not cands:
        return None
    return ObjectRef.body(min(cands, key=lambda b: b.mag).id)


def _planet_available(scene: SkyScene) -> bool:
    return scene.sun_alt < -4 and _brightest_planet(scene) is not None


def _planet_build(scene: SkyScene, level: int) -> LessonView:
    ref = _brightest_planet(scene)
    assert ref is not None
    b = scene.bodies[ref.key]
    steps = [
        f"1. Otoč se na {direction_name(b.az)} {direction_arrow(b.az)}.",
        f"2. Zvedni pohled {fist_text(b.alt)} nad obzor (pěst na natažené ruce ≈ 10°).",
        f"3. Hledej nejjasnější bod, který nebliká: to je {b.name}.",
    ]
    return _finish(scene, steps, [ref], [], level)


def _triangle_available(scene: SkyScene) -> bool:
    return _dark_enough(scene) and all(
        _alt(scene, _star(scene, n)) > 10 for n in ("Vega", "Deneb", "Altair")
    )


def _triangle_build(scene: SkyScene, level: int) -> LessonView:
    vega, deneb, altair = (_star(scene, n) for n in ("Vega", "Deneb", "Altair"))
    a_alt, a_az = _pos(scene, altair)
    v_alt, v_az = _pos(scene, vega)
    d_alt, d_az = _pos(scene, deneb)
    steps = [
        f"1. Podívej se {direction_word(a_az)} a zvedni pohled {fist_text(a_alt)}: najdeš "
        "Altair (s dvěma slabšími sousedy).",
        f"2. {direction_word(v_az).capitalize()}, {fist_text(v_alt)} nad obzorem: nejjasnější "
        "je Vega.",
        "3. " + position_sentence(d_alt, d_az).replace(".", "") + " je Deneb.",
    ]
    return _finish(
        scene,
        steps,
        [altair, vega, deneb],
        [(altair, vega), (vega, deneb)],
        level,
        asterism="summer_triangle",
        focus=altair,
    )


def _dipper_available(scene: SkyScene) -> bool:
    return _dark_enough(scene, 2.2) and _alt(scene, _star(scene, "Merak")) > 5


def _dipper_build(scene: SkyScene, level: int) -> LessonView:
    merak, dubhe, polaris = (_star(scene, n) for n in ("Merak", "Dubhe", "Polaris"))
    m_alt, m_az = _pos(scene, merak)
    p_alt, _ = _pos(scene, polaris)
    steps = [
        f"1. Najdi Velký vůz: sedm jasných hvězd {height_word(m_alt)} {direction_word(m_az)}.",
        "2. Spoj dvě zadní hvězdy vozu (Merak a Dubhe) a prodluž tu čáru asi pětkrát "
        "směrem od vozu.",
        f"3. Dojdeš k Polárce, {fist_text(p_alt)} nad obzorem na severu. Není moc jasná, "
        "ale stojí osaměle. Pod ní je sever.",
    ]
    return _finish(
        scene,
        steps,
        [merak, dubhe, polaris],
        [(merak, dubhe), (dubhe, polaris)],
        level,
        asterism="big_dipper",
        focus=polaris,
    )


def _cas_available(scene: SkyScene) -> bool:
    return _dark_enough(scene, 2.5) and _alt(scene, _star(scene, "Shedar")) > 10


def _cas_build(scene: SkyScene, level: int) -> LessonView:
    polaris, schedar = _star(scene, "Polaris"), _star(scene, "Shedar")
    s_alt, s_az = _pos(scene, schedar)
    steps = [
        "1. Najdi Polárku (předchozí úkol).",
        "2. Na druhé straně od Velkého vozu, zhruba stejně daleko, hledej pět hvězd ve "
        "tvaru písmene W nebo M.",
        f"3. Je to Kasiopeja, teď {height_word(s_alt)} {direction_word(s_az)}.",
    ]
    return _finish(
        scene,
        steps,
        [schedar, polaris],
        [(polaris, schedar)],
        level,
        asterism="cassiopeia_w",
        focus=schedar,
    )


def _peg_available(scene: SkyScene) -> bool:
    return _dark_enough(scene, 3.0) and _alt(scene, _star(scene, "Alpheratz")) > 15


def _peg_build(scene: SkyScene, level: int) -> LessonView:
    alpheratz, mirach, markab = (_star(scene, n) for n in ("Alpheratz", "Mirach", "Markab"))
    m31 = ObjectRef("dso", "M31")
    a_alt, a_az = _pos(scene, alpheratz)
    steps = [
        f"1. {direction_word(a_az).capitalize()} {height_word(a_alt)} hledej velký čtverec "
        "ze čtyř stejně jasných hvězd: Pegasův čtverec.",
        "2. Z jeho rohu Alpheratz vede řada hvězd k Mirachu.",
        "3. Od Mirachu jdi kolmo nahoru přes dvě slabé hvězdičky: mlhavá skvrnka je "
        "Galaxie v Andromedě, 2,5 milionu světelných let daleko.",
    ]
    return _finish(
        scene,
        steps,
        [alpheratz, mirach, m31, markab],
        [(alpheratz, mirach), (mirach, m31)],
        level,
        asterism="great_square",
        focus=m31,
    )


def _pleiades_available(scene: SkyScene) -> bool:
    return _dark_enough(scene, 3.0) and _alt(scene, ObjectRef("dso", "M45")) > 10


def _pleiades_build(scene: SkyScene, level: int) -> LessonView:
    m45 = ObjectRef("dso", "M45")
    alt, az = _pos(scene, m45)
    steps = [
        f"1. Podívej se {direction_word(az)}, {fist_text(alt)} nad obzor.",
        "2. Hledej malý shluk hvězd jako mlhavou skvrnku, menší než pěst.",
        "3. Když se podíváš kousek vedle (koutkem oka), uvidíš víc hvězd. To jsou Plejády.",
    ]
    return _finish(scene, steps, [m45], [], level)


def _orion_available(scene: SkyScene) -> bool:
    return _dark_enough(scene, 2.0) and _alt(scene, _star(scene, "Alnilam")) > 10


def _orion_build(scene: SkyScene, level: int) -> LessonView:
    belt = [_star(scene, n) for n in ("Alnitak", "Alnilam", "Mintaka")]
    betel, rigel = _star(scene, "Betelgeuse"), _star(scene, "Rigel")
    alt, az = _pos(scene, belt[1])
    steps = [
        f"1. {direction_word(az).capitalize()}, {fist_text(alt)} nad obzorem hledej tři "
        "stejně jasné hvězdy v řadě: Orionův pás.",
        "2. Nad pásem je oranžová Betelgeuze, pod ním modrobílý Rigel.",
    ]
    return _finish(
        scene,
        steps,
        [*belt, betel, rigel],
        [(belt[1], betel), (belt[1], rigel)],
        level,
        asterism="orion_belt",
        focus=belt[1],
    )


LESSONS: tuple[Lesson, ...] = (
    Lesson(
        "brightest_planet", "Najdi nejjasnější planetu dnes večer", _planet_available, _planet_build
    ),
    Lesson("summer_triangle", "Najdi Letní trojúhelník", _triangle_available, _triangle_build),
    Lesson("dipper_polaris", "Od Velkého vozu k Polárce", _dipper_available, _dipper_build),
    Lesson("cassiopeia", "W Kasiopeji", _cas_available, _cas_build),
    Lesson("pegasus_andromeda", "Pegasův čtverec a Andromeda", _peg_available, _peg_build),
    Lesson("pleiades", "Plejády", _pleiades_available, _pleiades_build),
    Lesson("orion", "Orion a jeho pás", _orion_available, _orion_build),
)
LESSON_BY_ID = {lesson.id: lesson for lesson in LESSONS}


def available_lessons(scene: SkyScene, done: list[str] | None = None) -> list[Lesson]:
    """Lessons that can be done right now; unfinished ones first, in course order."""
    done_set = set(done or [])
    avail = [lesson for lesson in LESSONS if lesson.available(scene)]
    return [x for x in avail if x.id not in done_set] + [x for x in avail if x.id in done_set]


@dataclass
class LessonProgress:
    """Current lesson, hint level and completion (persisted by the UI)."""

    done: list[str] = field(default_factory=list)
    current: str | None = None
    hint: int = 0

    def start(self, scene: SkyScene) -> Lesson | None:
        lessons = available_lessons(scene, self.done)
        if self.current and any(x.id == self.current for x in lessons):
            return LESSON_BY_ID[self.current]
        self.current = lessons[0].id if lessons else None
        self.hint = 0
        return LESSON_BY_ID[self.current] if self.current else None

    def found(self, scene: SkyScene) -> Lesson | None:
        """ "Našel jsem": mark done and move to the next available lesson."""
        if self.current and self.current not in self.done:
            self.done.append(self.current)
        self.current = None
        self.hint = 0
        return self.start(scene)

    def next_hint(self) -> int:
        self.hint = min(2, self.hint + 1)
        return self.hint

    def skip(self, scene: SkyScene) -> Lesson | None:
        lessons = available_lessons(scene, self.done)
        ids = [x.id for x in lessons]
        if self.current in ids and len(ids) > 1:
            self.current = ids[(ids.index(self.current) + 1) % len(ids)]
        self.hint = 0
        return LESSON_BY_ID[self.current] if self.current else None

    def position(self, scene: SkyScene) -> tuple[int, int]:
        """(number of the current lesson, total) for "ÚKOL 2 / 5"."""
        total = len(LESSONS)
        if self.current is None:
            return (min(len(self.done), total), total)
        return ([x.id for x in LESSONS].index(self.current) + 1, total)

    def next_title(self, scene: SkyScene) -> str | None:
        lessons = [x for x in available_lessons(scene, self.done) if x.id != self.current]
        return lessons[0].title if lessons else None
