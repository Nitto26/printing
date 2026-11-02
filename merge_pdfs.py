#!/usr/bin/env python3
"""
PDF Hierarchy Merger
Merges PDFs structured in nested folders:
  Main Folder -> Level-1 Folders -> Level-2 Subfolders -> PDF files
Traversal follows natural sort order (e.g. Folder 2 comes before Folder 10).
"""

import os
import sys
import re
import argparse
from pathlib import Path
from typing import List, Tuple
from pypdf import PdfWriter, PdfReader
from tqdm import tqdm


def natural_sort_key(s: str | Path):
    """
    Sort strings containing numbers naturally:
    e.g., ['folder1', 'folder2', 'folder10'] instead of ['folder1', 'folder10', 'folder2'].
    """
    name = s.name if isinstance(s, Path) else str(s)
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', name)]


def collect_pdf_files(main_folder: Path) -> List[Tuple[Path, Path, Path]]:
    """
    Traverses the directory structure:
      main_folder -> level_1_folder -> level_2_folder -> pdf files
    Returns a list of tuples: (level_1_path, level_2_path, pdf_path) in the specified traversal order.
    """
    if not main_folder.is_dir():
        raise NotADirectoryError(f"Main folder not found: {main_folder}")

    # Discover level 1 folders
    level_1_dirs = [d for d in main_folder.iterdir() if d.is_dir()]
    level_1_dirs.sort(key=natural_sort_key)

    collected: List[Tuple[Path, Path, Path]] = []

    for l1 in level_1_dirs:
        # Discover level 2 folders
        level_2_dirs = [d for d in l1.iterdir() if d.is_dir()]
        level_2_dirs.sort(key=natural_sort_key)

        for l2 in level_2_dirs:
            # Discover PDFs inside level 2 folder
            pdf_files = [
                f for f in l2.iterdir() 
                if f.is_file() and f.suffix.lower() == ".pdf"
            ]
            pdf_files.sort(key=natural_sort_key)

            for pdf in pdf_files:
                collected.append((l1, l2, pdf))

    return collected


def merge_pdfs(
    main_folder: Path,
    output_pdf: Path,
    add_bookmarks: bool = True,
    dry_run: bool = False
) -> int:
    """
    Gathers PDFs in hierarchical order and merges them into a single PDF.
    """
    print(f"\nScanning main folder: {main_folder.resolve()}")
    items = collect_pdf_files(main_folder)

    if not items:
        print("No PDF files found matching the 2-level folder structure.")
        return 0

    print(f"Discovered {len(items)} PDF file(s) across subfolders.\n")

    if dry_run:
        print("=== DRY RUN: Merge Sequence Preview ===")
        for idx, (l1, l2, pdf) in enumerate(items, 1):
            rel_path = pdf.relative_to(main_folder)
            print(f"  [{idx:3d}] {rel_path}")
        print("========================================")
        print("Dry run completed. No files were modified.")
        return len(items)

    writer = PdfWriter()
    current_l1 = None
    current_l2 = None
    l1_bookmark = None
    l2_bookmark = None
    total_pages = 0

    print("Merging PDFs in progress...")
    with tqdm(total=len(items), desc="Merging files", unit="pdf") as pbar:
        for l1, l2, pdf_path in items:
            pbar.set_postfix_str(pdf_path.name[:25])
            try:
                reader = PdfReader(str(pdf_path))
                num_pages = len(reader.pages)

                if num_pages == 0:
                    pbar.write(f"[WARNING] Skipping empty PDF: {pdf_path}")
                    pbar.update(1)
                    continue

                start_page_index = len(writer.pages)

                # Add bookmark hierarchy for easy navigation in PDF readers
                if add_bookmarks:
                    if l1 != current_l1:
                        current_l1 = l1
                        l1_bookmark = writer.add_outline_item(
                            title=l1.name,
                            page_number=start_page_index
                        )
                        current_l2 = None

                    if l2 != current_l2:
                        current_l2 = l2
                        l2_bookmark = writer.add_outline_item(
                            title=l2.name,
                            page_number=start_page_index,
                            parent=l1_bookmark
                        )

                    # Add file bookmark under subfolder
                    writer.add_outline_item(
                        title=pdf_path.name,
                        page_number=start_page_index,
                        parent=l2_bookmark
                    )

                # Append pages
                for page in reader.pages:
                    writer.add_page(page)

                total_pages += num_pages

            except Exception as e:
                pbar.write(f"[ERROR] Failed to process {pdf_path}: {e}")

            pbar.update(1)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pdf, "wb") as f_out:
        writer.write(f_out)

    print(f"\nSuccessfully created merged PDF!")
    print(f"Output File: {output_pdf.resolve()}")
    print(f"Total PDFs merged: {len(items)}")
    print(f"Total Pages: {total_pages}\n")

    return len(items)


def pick_folder_gui() -> str:
    """Opens a graphical folder selection dialog if available."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Select Main Folder containing subfolders of PDFs")
        root.destroy()
        return selected or ""
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Merge nested folder PDFs into a single combined PDF."
    )
    parser.add_argument(
        "-i", "--input",
        help="Path to the main folder containing the subfolders.",
        type=str,
        default=None
    )
    parser.add_argument(
        "-o", "--output",
        help="Path for the output merged PDF (default: <input_folder>/merged_output.pdf).",
        type=str,
        default=None
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the exact sequence of files that would be merged without writing anything."
    )
    parser.add_argument(
        "--no-bookmarks",
        action="store_true",
        help="Disable adding folder/file bookmarks (table of contents) to the output PDF."
    )

    args = parser.parse_args()

    input_path_str = args.input

    # If no input path provided, prompt GUI or terminal input
    if not input_path_str:
        print("No input folder provided.")
        gui_selected = pick_folder_gui()
        if gui_selected:
            input_path_str = gui_selected
        else:
            try:
                input_path_str = input("Enter path to the main folder: ").strip().strip('"').strip("'")
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled.")
                sys.exit(0)

    if not input_path_str:
        print("Error: No folder selected. Exiting.")
        sys.exit(1)

    main_dir = Path(input_path_str).resolve()
    if not main_dir.is_dir():
        print(f"Error: Directory '{main_dir}' does not exist.")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = main_dir / "merged_output.pdf"

    merge_pdfs(
        main_folder=main_dir,
        output_pdf=output_path,
        add_bookmarks=not args.no_bookmarks,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()

