from scout.app.dialogs.new_project_dialog import NewProjectDialog


def test_accept_with_all_required_fields_produces_values(qapp):
    dialog = NewProjectDialog()
    dialog.project_code_edit.setText("sol")
    dialog.location_code_edit.setText("rug")
    dialog.sublocation_code_edit.setText("crk")
    dialog.project_name_edit.setText("Calibration")

    dialog._on_accept()

    assert dialog.values() == {
        "project_code": "SOL", "location_code": "RUG", "sublocation_code": "CRK",
        "project_name": "Calibration",
    }


def test_accept_without_required_field_does_not_produce_values(qapp):
    dialog = NewProjectDialog()
    dialog.project_code_edit.setText("SOL")
    dialog.location_code_edit.setText("")  # missing
    dialog.sublocation_code_edit.setText("CRK")

    dialog._on_accept()

    assert dialog.values() is None


def test_project_name_is_optional(qapp):
    dialog = NewProjectDialog()
    dialog.project_code_edit.setText("SOL")
    dialog.location_code_edit.setText("RUG")
    dialog.sublocation_code_edit.setText("CRK")

    dialog._on_accept()

    assert dialog.values()["project_name"] == ""
