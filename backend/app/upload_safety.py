"""The Safety Checks every uploaded file passes before it becomes a Version (FR-09, T8).

All checks live here, so they are unit-testable without HTTP:

1. size: `read_capped` reads the upload in chunks and stops at the limit + 1
   byte; `validate` checks the size again;
2. magic bytes: PDF, JPEG and PNG only. The client's Content-Type is never
   looked at and the name never decides the type; a name whose extension
   says another type is a disguise (`type_mismatch`);
3. parse, clean or reject:
   - images: Pillow with a 50 MP cap (its bomb warning raised as an error),
     orientation applied, re-encoded in their own format (PNG lossless, JPEG
     quality 90), which drops EXIF/GPS and anything trailing;
   - PDFs: pikepdf with a page cap. JavaScript, Launch actions, embedded
     files, RichMedia, XFA and encryption are refused; a harmless
     /OpenAction, /AA or /AcroForm is stripped and the file re-saved. The
     parsed object tree is walked, never the raw bytes.

What passes is a `SafeFile` holding the cleaned bytes, which is what gets
stored. What fails is a `Rejection` with T8's reason code, HTTP status and a
plain sentence. There is no malware scan (a stated limit).
"""

import io
import unicodedata
import warnings
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

import pikepdf
from PIL import Image, ImageOps, UnidentifiedImageError

# Fixed in code (T8): the pixel cap, the accepted formats and the size ceiling.
MAX_IMAGE_PIXELS = 50_000_000
# Vercel refuses bodies over 4.5 MB (ADR 0003). Settings can't go above this.
FILE_SIZE_CEILING_MB = 4
SIZE_CEILING_BYTES = FILE_SIZE_CEILING_MB * 1024 * 1024
JPEG_QUALITY = 90
MAX_FILENAME_LENGTH = 255

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
# Above the cap Pillow only warns (it raises at twice the cap): make it an error.
warnings.simplefilter("error", Image.DecompressionBombWarning)

ReasonCode = Literal[
    "too_large",
    "unsupported_type",
    "type_mismatch",
    "corrupt",
    "pdf_active_content",
    "pdf_encrypted",
    "too_many_pages",
    "image_too_large",
]


@dataclass(frozen=True)
class Limits:
    max_bytes: int
    max_pdf_pages: int

    @classmethod
    def from_settings(cls, max_file_size_mb: int, max_pdf_pages: int) -> "Limits":
        return cls(min(max_file_size_mb * 1024 * 1024, SIZE_CEILING_BYTES), max_pdf_pages)


@dataclass(frozen=True)
class SafeFile:
    """The cleaned file, with the type detected from its content."""

    content: bytes
    content_type: str
    extension: str


@dataclass(frozen=True)
class Rejection:
    code: ReasonCode
    message: str

    @property
    def status(self) -> int:
        if self.code == "too_large":
            return 413
        if self.code in ("unsupported_type", "type_mismatch"):
            return 415
        return 422


@dataclass(frozen=True)
class _Format:
    content_type: str
    extension: str
    other_extensions: tuple[str, ...]
    pillow: str | None


_PDF = _Format("application/pdf", "pdf", (), None)
_JPEG = _Format("image/jpeg", "jpg", ("jpeg", "jpe"), "JPEG")
_PNG = _Format("image/png", "png", (), "PNG")
_SIGNATURES = ((b"%PDF-", _PDF), (b"\xff\xd8\xff", _JPEG), (b"\x89PNG\r\n\x1a\n", _PNG))


def too_large(max_bytes: int) -> Rejection:
    return Rejection(
        "too_large", f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit."
    )


async def read_capped(chunks: AsyncIterator[bytes], max_bytes: int) -> bytes | Rejection:
    """Read a stream, giving up as soon as it passes `max_bytes`."""
    buf = bytearray()
    async for chunk in chunks:
        buf += chunk
        if len(buf) > max_bytes:
            return too_large(max_bytes)
    return bytes(buf)


def sanitise_filename(name: str | None) -> str | None:
    """The original name, for display and downloads only: the last path part,
    with control characters and separators stripped, at most 255 characters
    (the extension kept). None when nothing is left."""
    if not name:
        return None
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if not unicodedata.category(c).startswith("C")).strip()
    if not name:
        return None
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        keep = f"{dot}{ext}" if dot and len(ext) <= 10 else ""
        name = name[: MAX_FILENAME_LENGTH - len(keep)] + keep
    return name


def validate(data: bytes, limits: Limits, *, filename: str | None = None) -> SafeFile | Rejection:
    """Run the Safety Checks on a whole file; return it cleaned or refused."""
    if len(data) > limits.max_bytes:
        return too_large(limits.max_bytes)

    fmt = next((f for magic, f in _SIGNATURES if data.startswith(magic)), None)
    if fmt is None:
        return Rejection("unsupported_type", "Only PDF, JPEG and PNG files are accepted.")
    if _disguised(filename, fmt):
        return Rejection(
            "type_mismatch",
            f"The file's name says another type, but its content is a "
            f"{fmt.extension.upper()} file.",
        )

    if fmt is _PDF:
        return _clean_pdf(data, limits.max_pdf_pages)
    return _clean_image(data, fmt)


def _disguised(filename: str | None, fmt: _Format) -> bool:
    if not filename or "." not in filename.strip("."):
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension not in (fmt.extension, *fmt.other_extensions)


# --- Images ------------------------------------------------------------------------------


def _clean_image(data: bytes, fmt: _Format) -> SafeFile | Rejection:
    corrupt = Rejection("corrupt", "The image file is damaged or incomplete.")
    try:
        with Image.open(io.BytesIO(data), formats=[fmt.pillow]) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                return _image_too_large()
            image.load()
            upright = ImageOps.exif_transpose(image)
            out = io.BytesIO()
            if fmt is _JPEG:
                upright.save(out, format="JPEG", quality=JPEG_QUALITY)
            else:
                upright.save(out, format="PNG")
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return _image_too_large()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return corrupt
    return SafeFile(out.getvalue(), fmt.content_type, fmt.extension)


def _image_too_large() -> Rejection:
    return Rejection(
        "image_too_large",
        f"The image has more than {MAX_IMAGE_PIXELS // 1_000_000} megapixels.",
    )


# --- PDFs --------------------------------------------------------------------------------

# Names that mean active content, wherever they appear as a key or a value.
_ACTIVE = frozenset(
    {
        "/JavaScript", "/JS", "/Launch", "/EmbeddedFile", "/EmbeddedFiles", "/EF",
        "/RichMedia", "/RichMediaContent", "/RichMediaSettings", "/XFA",
    }
)
# Harmless once it carries no active content: stripped, not refused.
_STRIPPED_FROM_ROOT = ("/OpenAction", "/AA", "/AcroForm")


def _clean_pdf(data: bytes, max_pages: int) -> SafeFile | Rejection:
    encrypted = Rejection("pdf_encrypted", "Password-protected or encrypted PDFs are not accepted.")
    corrupt = Rejection("corrupt", "The PDF file is damaged or can't be read.")
    try:
        with pikepdf.open(io.BytesIO(data)) as pdf:
            if pdf.is_encrypted:
                return encrypted
            pages = len(pdf.pages)
            if pages == 0:
                return corrupt
            if pages > max_pages:
                return Rejection(
                    "too_many_pages", f"The PDF has {pages} pages; the limit is {max_pages}."
                )
            if _has_active_content(pdf):
                return Rejection(
                    "pdf_active_content",
                    "The PDF contains active content (scripts, launch actions, embedded "
                    "files, rich media or XFA forms).",
                )
            _strip_auto_actions(pdf)
            out = io.BytesIO()
            pdf.save(out)
    except pikepdf.PasswordError:
        return encrypted
    except (pikepdf.PdfError, ValueError, RecursionError):
        return corrupt
    return SafeFile(out.getvalue(), _PDF.content_type, _PDF.extension)


def _children(obj: pikepdf.Object):
    """(key name or None, value) for each direct child of a dictionary,
    stream or array."""
    if isinstance(obj, pikepdf.Stream):
        obj = obj.stream_dict
    if isinstance(obj, pikepdf.Dictionary):
        for key in obj.keys():
            yield key, obj.get(key)
    elif isinstance(obj, pikepdf.Array):
        for item in obj:
            yield None, item


def _walk(pdf: pikepdf.Pdf):
    """Every (key, value) pair reachable from the trailer, each indirect
    object visited once."""
    seen: set[tuple[int, int]] = set()
    stack: list[pikepdf.Object] = [pdf.trailer]
    while stack:
        obj = stack.pop()
        if obj.is_indirect:
            if obj.objgen in seen:
                continue
            seen.add(obj.objgen)
        for key, value in _children(obj):
            yield key, value
            if isinstance(value, (pikepdf.Dictionary, pikepdf.Array, pikepdf.Stream)):
                stack.append(value)


def _has_active_content(pdf: pikepdf.Pdf) -> bool:
    if "/Encrypt" in pdf.trailer:
        return True
    for key, value in _walk(pdf):
        if key in _ACTIVE:
            return True
        if isinstance(value, pikepdf.Name) and str(value) in _ACTIVE:
            return True
    return False


def _strip_auto_actions(pdf: pikepdf.Pdf) -> None:
    """Drop the document's open action, form layer and every additional-actions
    (/AA) entry, on pages and annotations too."""
    for key in _STRIPPED_FROM_ROOT:
        if key in pdf.Root:
            del pdf.Root[key]
    for page in pdf.pages:
        if "/AA" in page.obj:
            del page.obj["/AA"]
        for annot in page.obj.get("/Annots", pikepdf.Array()):
            if isinstance(annot, pikepdf.Dictionary) and "/AA" in annot:
                del annot["/AA"]
