from amazon_music_desktop.browser.download_policy import (
    safe_filename,
    validate_destination,
)


def test_safe_filename_traversal():
    assert safe_filename("../../etc/passwd") == "passwd"


def test_safe_filename_empty():
    assert safe_filename("") == "download"


def test_validate_destination_inside(tmp_path):
    target = validate_destination(tmp_path, "file.txt")
    assert target is not None
    assert str(target).startswith(str(tmp_path))


def test_validate_destination_traversal(tmp_path):
    # safe_filename strips traversal, so result inside; but direct .. name sanitized
    target = validate_destination(tmp_path, "../secret.txt")
    assert target is not None
    assert tmp_path in target.parents or target.parent == tmp_path
