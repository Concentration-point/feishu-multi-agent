from pathlib import Path


def main():
    """Optional hook. Implement with LibreOffice, PowerPoint COM, or unoconv if available."""
    print("Preview export is environment-specific.")
    print("Recommended outputs: output/deck.pdf and output/previews/slide_01.png ...")
    print("On Windows with PowerPoint installed, add a COM export implementation here.")


if __name__ == "__main__":
    main()
