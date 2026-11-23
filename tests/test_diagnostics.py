from dualcontrol.models import ConnectionState
from dualcontrol.services.diagnostics import acceptance_checklist, hex_dump


def test_hex_dump_empty():
    assert hex_dump(None) == "(sin datos todavía)"


def test_hex_dump_formats_bytes():
    dump = hex_dump(bytes([0x02, 0xFF, 0x00, 0x01]))
    assert "02 FF 00 01" in dump


def test_acceptance_checklist_marks_profiles_as_verified_regardless_of_hardware():
    items = acceptance_checklist(using_real_backend=False, connection_state=ConnectionState.NOT_DETECTED)
    profile_item = next(i for i in items if "perfiles" in i.description.lower())
    assert profile_item.verified is True


def test_acceptance_checklist_output_depends_on_connection_state():
    not_connected = acceptance_checklist(using_real_backend=True, connection_state=ConnectionState.NOT_DETECTED)
    connected = acceptance_checklist(using_real_backend=True, connection_state=ConnectionState.OUTPUT_OK)

    detect_item_1 = next(i for i in not_connected if "Detecta" in i.description)
    detect_item_2 = next(i for i in connected if "Detecta" in i.description)
    assert detect_item_1.verified is False
    assert detect_item_2.verified is True


def test_acceptance_checklist_triggers_and_executable_flags():
    before = acceptance_checklist(
        using_real_backend=True,
        connection_state=ConnectionState.OUTPUT_OK,
        physical_triggers_tested=False,
        executable_ready=False,
    )
    after = acceptance_checklist(
        using_real_backend=True,
        connection_state=ConnectionState.OUTPUT_OK,
        physical_triggers_tested=True,
        reconnection_verified=True,
        executable_ready=True,
    )
    assert next(i for i in before if "efectos físicos" in i.description.lower()).verified is False
    assert next(i for i in before if "ejecutable" in i.description.lower()).verified is False
    assert next(i for i in after if "efectos físicos" in i.description.lower()).verified is True
    assert next(i for i in after if "desconexiones" in i.description.lower()).verified is True
    assert next(i for i in after if "ejecutable" in i.description.lower()).verified is True
