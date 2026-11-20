"""XMLDSig signing for DGII e-CF documents (RSA-SHA256, inclusive C14N)."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

DSIG = "http://www.w3.org/2000/09/xmldsig#"
C14N_INCLUSIVE = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

_SIGNATURE_VALUE_RE = re.compile(
    r"<(?:[\w]+:)?SignatureValue[^>]*>([\s\S]*?)</(?:[\w]+:)?SignatureValue>"
)


def _ds(name: str) -> str:
    return f"{{{DSIG}}}{name}"


def _canonicalize(node: etree._Element) -> bytes:
    """Inclusive C14N 1.0 without comments.

    Re-parse a serialized subtree so lxml does not emit spurious xmlns=\"\"
    attributes that would break DGII's .NET verifier.
    """
    standalone = etree.fromstring(etree.tostring(node))
    return etree.tostring(
        standalone, method="c14n", exclusive=False, with_comments=False
    )


@dataclass(frozen=True)
class SigningCredentials:
    key: rsa.RSAPrivateKey
    certificate: x509.Certificate


def load_p12(path: str | Path, password: str) -> SigningCredentials:
    data = Path(path).read_bytes()
    key, certificate, _ = pkcs12.load_key_and_certificates(
        data, password.encode("utf-8") if password else None
    )
    if key is None or certificate is None:
        raise ValueError("PKCS#12 must contain a private key and certificate")
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("DGII signing requires an RSA private key")
    return SigningCredentials(key=key, certificate=certificate)


class Signer:
    def __init__(self, credentials: SigningCredentials) -> None:
        self._key = credentials.key
        self._certificate = credentials.certificate

    @classmethod
    def from_p12(cls, path: str | Path, password: str) -> Signer:
        return cls(load_p12(path, password))

    def sign_xml(self, xml: str) -> str:
        """Sign ``xml`` and return the signed document with XML declaration."""
        parser = etree.XMLParser(remove_blank_text=True, remove_comments=True)
        root = etree.fromstring(xml.encode("utf-8"), parser=parser)
        self._sign_element(root)
        body = etree.tostring(root, encoding="unicode")
        return f'<?xml version="1.0" encoding="utf-8"?>{body}'

    def _sign_element(self, root: etree._Element) -> None:
        digest = hashlib.sha256(_canonicalize(root)).digest()

        signature = etree.Element(_ds("Signature"), nsmap={None: DSIG})
        signed_info = etree.SubElement(signature, _ds("SignedInfo"))
        etree.SubElement(signed_info, _ds("CanonicalizationMethod")).set(
            "Algorithm", C14N_INCLUSIVE
        )
        etree.SubElement(signed_info, _ds("SignatureMethod")).set(
            "Algorithm", RSA_SHA256
        )
        reference = etree.SubElement(signed_info, _ds("Reference"))
        reference.set("URI", "")
        transforms = etree.SubElement(reference, _ds("Transforms"))
        etree.SubElement(transforms, _ds("Transform")).set("Algorithm", ENVELOPED)
        etree.SubElement(transforms, _ds("Transform")).set(
            "Algorithm", C14N_INCLUSIVE
        )
        etree.SubElement(reference, _ds("DigestMethod")).set("Algorithm", SHA256)
        etree.SubElement(reference, _ds("DigestValue")).text = base64.b64encode(
            digest
        ).decode("ascii")

        # Attach Signature before signing SignedInfo so namespace context matches.
        root.append(signature)

        signature_bytes = self._key.sign(
            _canonicalize(signed_info),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        etree.SubElement(signature, _ds("SignatureValue")).text = base64.b64encode(
            signature_bytes
        ).decode("ascii")

        key_info = etree.SubElement(signature, _ds("KeyInfo"))
        x509_data = etree.SubElement(key_info, _ds("X509Data"))
        etree.SubElement(x509_data, _ds("X509Certificate")).text = base64.b64encode(
            self._certificate.public_bytes(serialization.Encoding.DER)
        ).decode("ascii")


def extract_security_code(signed_xml: str) -> str:
    """First 6 characters of SignatureValue with whitespace removed."""
    match = _SIGNATURE_VALUE_RE.search(signed_xml)
    if not match:
        raise ValueError("SignatureValue not found in signed XML")
    value = re.sub(r"\s+", "", match.group(1))
    if len(value) < 6:
        raise ValueError("SignatureValue is too short for a security code")
    return value[:6]
