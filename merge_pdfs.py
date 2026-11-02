#!/usr/bin/env python3
"""
PDF Hierarchy Merger
Merges nested PDFs per first-level folder:
  Main Folder/
  ├── Folder A/                  -> merged into 'A.pdf'
  │   ├── Subfolder P/
  │   │   ├── doc_1.pdf
  │   │   └── doc_2.pdf
  │   ├── Subfolder Q/
  │   │   ├── doc_1.pdf
  │   │   └── doc_2.pdf
  │   └── ...
  ├── Folder B/                  -> merged into 'B.pdf'
  │   ├── Subfolder P/
  │   └── ...
"""

import os
import sys
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Dict
from pypdf import PdfWriter, PdfReader
from tqdm import tqdm


def natural_sort_key(s: str | Path):
    """
    Sort strings containing numbers naturally:
    e.g., ['folder1', 'folder2', 'folder10'] instead of ['folder1', 'folder10', 'folder2'].
    """
    name = s.name if isinstance(s, Path) else str(s)
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', name)]


def collect_pdfs_by_parent(main_folder: Path, exclude_dir_names: set = None) -> Dict[Path, List[Tuple[Path, Path]]]:
    """
    Scans the directory structure:
      main_folder -> Level-1 Folders (A, B, C...) -> Level-2 Subfolders (P, Q, R...) -> PDF files
    
    Returns a dictionary mapping:
      Level-1 Folder Path -> List of (Level-2 Subfolder Path, PDF Path)
    """
    if not main_folder.is_dir():
        raise NotADirectoryError(f"Main folder not found: {main_folder}")

    if exclude_dir_names is None:
        exclude_dir_names = {"merged_pdfs", "merged_outputs"}

    level_1_dirs = [
        d for d in main_folder.iterdir() 
        if d.is_dir() and d.name not in exclude_dir_names
    ]
    level_1_dirs.sort(key=natural_sort_key)

    result: Dict[Path, List[Tuple[Path, Path]]] = {}

    for l1 in level_1_dirs:
        level_2_dirs = [d for d in l1.iterdir() if d.is_dir()]
        level_2_dirs.sort(key=natural_sort_key)

        folder_pdfs: List[Tuple[Path, Path]] = []
        for l2 in level_2_dirs:
            pdf_files = [
                f for f in l2.iterdir() 
                if f.is_file() and f.suffix.lower() == ".pdf"
            ]
            pdf_files.sort(key=natural_sort_key)

            for pdf in pdf_files:
                folder_pdfs.append((l2, pdf))

        if folder_pdfs:
            result[l1] = folder_pdfs

    return result


def merge_single_folder(
    parent_folder: Path,
    items: List[Tuple[Path, Path]],
    output_pdf: Path,
    add_bookmarks: bool = True
) -> int:
    """
    Merges all PDFs belonging to one Level-1 folder into a single PDF file.
    """
    writer = PdfWriter()
    current_l2 = None
    l2_bookmark = None
    total_pages = 0

    for l2, pdf_path in items:
        try:
            reader = PdfReader(str(pdf_path))
            num_pages = len(reader.pages)
            if num_pages == 0:
                continue

            start_page_index = len(writer.pages)

            if add_bookmarks:
                if l2 != current_l2:
                    current_l2 = l2
                    l2_bookmark = writer.add_outline_item(
                        title=l2.name,
                        page_number=start_page_index
                    )

                writer.add_outline_item(
                    title=pdf_path.name,
                    page_number=start_page_index,
                    parent=l2_bookmark
                )

            for page in reader.pages:
                writer.add_page(page)

            total_pages += num_pages

        except Exception as e:
            print(f"\n[ERROR] Failed to read {pdf_path}: {e}")

    if total_pages > 0:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with open(output_pdf, "wb") as f_out:
            writer.write(f_out)

    return total_pages


def process_batches(
    main_folder: Path,
    output_dir: Path,
    add_bookmarks: bool = True,
    dry_run: bool = False
):
    """
    Processes all Level-1 folders and produces <folder_name>.pdf for each.
    """
    print(f"\nScanning main folder: {main_folder.resolve()}")
    grouped_data = collect_pdfs_by_parent(main_folder, exclude_dir_names={output_dir.name})

    if not grouped_data:
        print("No Level-1 folders with PDFs found.")
        return

    total_folders = len(grouped_data)
    total_files = sum(len(items) for items in grouped_data.values())
    print(f"Found {total_folders} parent folder(s) containing a total of {total_files} PDF(s).\n")

    if dry_run:
        print("=== DRY RUN: Preview of Output PDFs to be Created ===")
        for idx, (l1, items) in enumerate(grouped_data.items(), 1):
            target_name = f"{l1.name}.pdf"
            print(f"\n[{idx}/{total_folders}] Parent Folder: '{l1.name}' --> '{target_name}' ({len(items)} PDFs):")
            for l2, pdf in items:
                print(f"      - {l2.name} / {pdf.name}")
        print("\n" + "=" * 54)
        print("Dry run completed. No files were written.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Merged PDFs will be saved to: {output_dir.resolve()}\n")

    successful_merges = 0
    total_pages_generated = 0

    with tqdm(total=total_folders, desc="Processing folders", unit="folder") as pbar:
        for l1, items in grouped_data.items():
            target_pdf = output_dir / f"{l1.name}.pdf"
            pbar.set_postfix_str(f"Merging -> {target_pdf.name}")

            pages = merge_single_folder(
                parent_folder=l1,
                items=items,
                output_pdf=target_pdf,
                add_bookmarks=add_bookmarks
            )

            if pages > 0:
                successful_merges += 1
                total_pages_generated += pages

            pbar.update(1)

    print("\n" + "=" * 54)
    print(f"Done! Successfully created {successful_merges} merged PDF file(s).")
    print(f"Total Pages Generated: {total_pages_generated}")
    print(f"Output Directory: {output_dir.resolve()}")
    print("=" * 54 + "\n")


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
        description="Merge nested PDFs per first-level folder into <folder_name>.pdf"
    )
    parser.add_argument(
        "-i", "--input",
        help="Path to the main folder containing the first bunch of folders (a, b, c...).",
        type=str,
        default=None
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Directory to save the merged PDFs (default: <main_folder>/merged_pdfs).",
        type=str,
        default=None
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the exact structure and files to be merged without writing anything."
    )
    parser.add_argument(
        "--no-bookmarks",
        action="store_true",
        help="Disable adding subfolder/file bookmarks (table of contents) to each output PDF."
    )

    args = parser.parse_args()

    input_path_str = args.input

    # If no input provided, prompt GUI or terminal input
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

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = main_dir / "merged_pdfs"

    process_batches(
        main_folder=main_dir,
        output_dir=output_dir,
        add_bookmarks=not args.no_bookmarks,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
