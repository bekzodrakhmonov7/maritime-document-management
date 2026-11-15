"""The Safety Checks (FR-09, T8): every reason code, plus the cleaned output.

`upload_safety.validate` runs without HTTP, on bytes and limits.
"""

import io

import pikepdf
import pytest
from PIL import Image

from app.upload_safety import (
    MAX_IMAGE_PIXELS,
    Limits,
    Rejection,
    SafeFile,
    read_capped,
    sanitise_filename,
    validate,
)

LIMITS = Limits(max_bytes=1024 * 1024, max_pdf_pages=3)


def _image(fmt: str, size=(40, 20), **save) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format=fmt, **save)
    return buf.getvalue()


def _pdf(pages: int = 1, build=None, **save) -> bytes:
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page()
    if build:
        build(pdf)
    buf = io.BytesIO()
    pdf.save(buf, **save)
    return buf.getvalue()


def _rejected(result, code: str, status: int) -> None:
    assert isinstance(result, Rejection), result
    assert (result.code, result.status) == (code, status)
    assert result.message.endswith(".")


# --- Size --------------------------------------------------------------------------------


def test_a_file_over_the_size_limit_is_too_large():
    _rejected(validate(b"%PDF-" + b"0" * LIMITS.max_bytes, LIMITS), "too_large", 413)


async def _chunks(*parts: bytes):
    for part in parts:
        yield part


async def test_the_streamed_read_stops_at_the_limit_plus_one():
    seen = []

    async def counted():
        for i in range(10):
            seen.append(i)
            yield b"x" * 400

    result = await read_capped(counted(), 1000)
    _rejected(result, "too_large", 413)
    assert len(seen) == 3  # 1200 bytes > 1000: nothing after that is read


async def test_the_streamed_read_returns_a_file_at_the_limit():
    assert await read_capped(_chunks(b"a" * 600, b"b" * 400), 1000) == b"a" * 600 + b"b" * 400


# --- Magic bytes -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [b"", b"GIF89a....", b"PK\x03\x04 zip", b"MZ\x90\x00 exe", _image("GIF"), b"<html>%PDF-"],
)
def test_anything_but_pdf_jpeg_or_png_is_unsupported(data):
    _rejected(validate(data, LIMITS), "unsupported_type", 415)


def test_a_disguised_file_is_a_type_mismatch():
    _rejected(validate(_image("PNG"), LIMITS, filename="passport.pdf"), "type_mismatch", 415)
    _rejected(validate(_pdf(), LIMITS, filename="scan.jpg"), "type_mismatch", 415)
    _rejected(validate(_image("JPEG"), LIMITS, filename="photo.exe"), "type_mismatch", 415)


def test_the_name_never_decides_the_type():
    for name in (None, "scan", "SCAN.JPEG", "scan.jpg"):
        result = validate(_image("JPEG"), LIMITS, filename=name)
        assert isinstance(result, SafeFile)
        assert (result.content_type, result.extension) == ("image/jpeg", "jpg")


# --- Images ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xd8\xff\xe0 not really a jpeg",
        b"\x89PNG\r\n\x1a\n not really a png",
        _image("PNG")[:60],
    ],
)
def test_a_broken_image_is_corrupt(data):
    _rejected(validate(data, LIMITS), "corrupt", 422)


def test_an_image_over_the_pixel_cap_is_too_large():
    # A 1-bit PNG keeps the file small while the pixel count is huge.
    buf = io.BytesIO()
    Image.new("1", (10_000, MAX_IMAGE_PIXELS // 10_000 + 1)).save(buf, format="PNG")
    _rejected(validate(buf.getvalue(), Limits(4 * 1024 * 1024, 50)), "image_too_large", 422)


def test_a_jpeg_is_re_encoded_upright_without_exif_gps_or_trailing_data():
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to display
    exif[0x8825] = {2: (50.0, 1.0, 0.0)}  # GPSInfo latitude
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (10, 120, 200)).save(buf, format="JPEG", exif=exif)
    data = buf.getvalue() + b"TRAILING-PAYLOAD"

    result = validate(data, LIMITS, filename="photo.jpeg")

    assert isinstance(result, SafeFile)
    assert (result.content_type, result.extension) == ("image/jpeg", "jpg")
    assert b"TRAILING-PAYLOAD" not in result.content
    cleaned = Image.open(io.BytesIO(result.content))
    assert cleaned.format == "JPEG"
    assert cleaned.size == (20, 40)  # orientation applied
    assert not cleaned.getexif()


def test_a_png_is_re_encoded_losslessly_without_metadata():
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "secret")
    original = Image.new("RGB", (16, 16))
    original.putpixel((3, 4), (1, 2, 3))
    buf = io.BytesIO()
    original.save(buf, format="PNG", pnginfo=info)
    data = buf.getvalue() + b"<script>trailing</script>"

    result = validate(data, LIMITS)

    assert isinstance(result, SafeFile)
    assert (result.content_type, result.extension) == ("image/png", "png")
    assert b"secret" not in result.content and b"<script>" not in result.content
    cleaned = Image.open(io.BytesIO(result.content))
    assert cleaned.getpixel((3, 4)) == (1, 2, 3)
    assert "Comment" not in cleaned.info


# --- PDFs --------------------------------------------------------------------------------


def test_a_plain_pdf_is_re_saved():
    result = validate(_pdf(2), LIMITS, filename="cert.pdf")
    assert isinstance(result, SafeFile)
    assert (result.content_type, result.extension) == ("application/pdf", "pdf")
    assert len(pikepdf.open(io.BytesIO(result.content)).pages) == 2


@pytest.mark.parametrize("data", [b"%PDF-1.7\nthis is not a pdf at all", _pdf()[:40]])
def test_a_broken_pdf_is_corrupt(data):
    _rejected(validate(data, LIMITS), "corrupt", 422)


def test_a_pdf_over_the_page_limit_is_refused():
    assert isinstance(validate(_pdf(3), LIMITS), SafeFile)
    _rejected(validate(_pdf(4), LIMITS), "too_many_pages", 422)


@pytest.mark.parametrize("user_password", ["", "secret"])
def test_an_encrypted_pdf_is_refused(user_password):
    data = _pdf(encryption=pikepdf.Encryption(owner="owner", user=user_password))
    _rejected(validate(data, LIMITS), "pdf_encrypted", 422)


def _open_action_js(pdf):
    pdf.Root.OpenAction = pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String("app.alert(1)"))


def _names_javascript(pdf):
    script = pdf.make_indirect(pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String("x")))
    pdf.Root.Names = pikepdf.Dictionary(
        JavaScript=pikepdf.Dictionary(Names=pikepdf.Array([pikepdf.String("a"), script]))
    )


def _page_annotation_launch(pdf):
    pdf.pages[0].Annots = pdf.make_indirect(pikepdf.Array([
        pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
            Rect=[0, 0, 10, 10],
            A=pikepdf.Dictionary(S=pikepdf.Name.Launch, F=pikepdf.String("calc.exe")),
        )
    ]))


def _embedded_file(pdf):
    pdf.attachments["payload.exe"] = pikepdf.AttachedFileSpec(pdf, b"MZ...", mime_type="application/octet-stream")


def _rich_media(pdf):
    pdf.pages[0].Annots = pdf.make_indirect(pikepdf.Array([
        pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.RichMedia, Rect=[0, 0, 5, 5])
    ]))


def _xfa(pdf):
    pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array(), XFA=pikepdf.String("<xdp/>"))


def _page_aa_javascript(pdf):
    pdf.pages[0].AA = pikepdf.Dictionary(
        O=pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String("x"))
    )


@pytest.mark.parametrize(
    "build",
    [_open_action_js, _names_javascript, _page_annotation_launch, _embedded_file, _rich_media, _xfa,
     _page_aa_javascript],
)
def test_active_pdf_content_is_refused(build):
    _rejected(validate(_pdf(build=build), LIMITS), "pdf_active_content", 422)


def test_javascript_hidden_in_an_object_stream_is_still_found():
    data = _pdf(build=_open_action_js, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    assert b"/JavaScript" not in data  # not visible in the raw bytes
    _rejected(validate(data, LIMITS), "pdf_active_content", 422)


def test_harmless_auto_actions_and_form_layers_are_stripped():
    def build(pdf):
        page = pdf.pages[0]
        pdf.Root.OpenAction = pikepdf.Array([page.obj, pikepdf.Name.Fit])
        pdf.Root.AA = pikepdf.Dictionary(WC=pikepdf.Dictionary(S=pikepdf.Name.GoTo, D=pikepdf.Array([page.obj, pikepdf.Name.Fit])))
        pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array())
        page.AA = pikepdf.Dictionary(O=pikepdf.Dictionary(S=pikepdf.Name.GoTo, D=pikepdf.Array([page.obj, pikepdf.Name.Fit])))

    result = validate(_pdf(build=build), LIMITS)

    assert isinstance(result, SafeFile)
    cleaned = pikepdf.open(io.BytesIO(result.content))
    for key in ("/OpenAction", "/AA", "/AcroForm"):
        assert key not in cleaned.Root
    assert "/AA" not in cleaned.pages[0]


# --- Filenames ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, cleaned",
    [
        ("passport.pdf", "passport.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\anna\\scan.jpg", "scan.jpg"),
        ("bad\x00na\x1fme\x7f.png", "badname.png"),
        ("  spaced name.pdf  ", "spaced name.pdf"),
        ("", None),
        ("/", None),
        (None, None),
    ],
)
def test_filenames_are_sanitised(raw, cleaned):
    assert sanitise_filename(raw) == cleaned


def test_long_filenames_are_cut_to_255_characters():
    assert len(sanitise_filename("a" * 300 + ".pdf")) == 255


def test_the_size_ceiling_is_4_mb_whatever_the_setting():
    # Vercel refuses request bodies over 4.5 MB (ADR-0003).
    assert Limits.from_settings(4, 50).max_bytes == 4 * 1024 * 1024
    assert Limits.from_settings(25, 50).max_bytes == 4 * 1024 * 1024
