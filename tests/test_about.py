from pathlib import Path

import yaml

from anexis.profile.about import SECTIONS, export_profile, import_profile

REPO = Path(__file__).parent.parent


def about(memory):
    return sorted(m.text for m in memory.pinned())


def test_import_turns_each_answer_into_a_pinned_about_me_memory(memory):
    report = import_profile(memory, {"name": "Sam", "age": 19, "classes": ["Chem 101 Mon 9am", "Calc 2 Tue 1pm"]})
    assert about(memory) == ["Age: 19", "Class this term: Calc 2 Tue 1pm", "Class this term: Chem 101 Mon 9am", "Name: Sam"]
    assert all(m.source == "about_me" for m in memory.pinned())
    assert report["added"] == 4
    assert [m.kind for m in memory.pinned() if "Class" in m.text] == ["class", "class"]


def test_importing_again_updates_what_changed_without_duplicates(memory):
    import_profile(memory, {"name": "Sam", "age": 19})
    report = import_profile(memory, {"name": "Sam", "age": 20})
    assert about(memory) == ["Age: 20", "Name: Sam"]
    assert (report["added"], report["changed"], report["same"]) == (0, 1, 1)


def test_dropping_an_item_from_a_list_removes_it(memory):
    import_profile(memory, {"classes": ["Chem 101", "Calc 2"]})
    import_profile(memory, {"classes": ["Calc 2"]})
    assert about(memory) == ["Class this term: Calc 2"]


def test_sections_left_out_of_an_import_are_untouched(memory):
    import_profile(memory, {"name": "Sam", "habits": ["Runs every morning"]})
    import_profile(memory, {"age": 19})
    assert about(memory) == ["Age: 19", "Habit: Runs every morning", "Name: Sam"]


def test_blank_answers_are_skipped(memory):
    import_profile(memory, {"name": "", "age": None, "classes": [], "work": "   "})
    assert about(memory) == []


def test_nested_answers_and_unknown_sections_are_still_kept(memory):
    import_profile(memory, {"school": {"name": "State U", "major": "Biology"}, "favorite_snack": "pretzels"})
    assert about(memory) == ["Favorite snack: pretzels", "School major: Biology", "School name: State U"]


def test_export_gives_back_what_was_imported(memory):
    data = {"name": "Sam", "age": "19", "classes": ["Chem 101", "Calc 2"], "habits": ["Runs every morning"]}
    import_profile(memory, data)
    assert export_profile(memory) == data


def test_the_template_in_the_repo_covers_every_section_and_nothing_else():
    template = yaml.safe_load((REPO / "profile" / "about_me.example.yaml").read_text())
    assert list(template) == [s.key for s in SECTIONS]


def test_about_me_shows_up_in_search_too(memory):
    import_profile(memory, {"areas": ["Downtown campus", "East side"]})
    assert "Downtown campus" in memory.search("campus")[0].text
