import argparse
import os
from os import PathLike
import logging

from datasets import load_dataset
from model import DecoderBase, make_model
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)


def translate(args, workdir: PathLike, model: DecoderBase):

    EXTENSIONS = { "C": ".c", "C++": ".cpp", "Java": ".java", "Python": ".py", "Go": ".go" }

    with Progress(
        TextColumn(
            f"{args.dataset} •" + "[progress.percentage]{task.percentage:>3.0f}%"
        ),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
    ) as p:
        if args.dataset == "codenet":
            dataset = load_dataset("icatlab-uiuc/codenet")

        elif args.dataset == "avatar":
            dataset = load_dataset("icatlab-uiuc/avatar")

        for item in p.track(dataset['train']):

            if item['language'] != args.source_lang:
                continue

            p_name = item['id']
            os.makedirs(os.path.join(workdir, p_name), exist_ok=True)
            log = f"Translate: {p_name} from {args.source_lang}-{args.dataset} to {args.target_lang} using {args.model}"
            n_existing = 0
            if args.resume:
                # count existing translated files
                n_existing = len(
                    [
                        f
                        for f in os.listdir(os.path.join(workdir, p_name))
                        if f.endswith(EXTENSIONS[args.target_lang])
                    ]
                )
                if n_existing > 0:
                    log += f" (resuming from {n_existing})"

            nsamples = args.n_samples - n_existing
            p.console.print(log)

            sidx = args.n_samples - nsamples
            while sidx < args.n_samples:
                prompt = f"{args.source_lang}:\n{item['code']}\n\nTranslate the above {args.source_lang} code to {args.target_lang} and end with comment \"<END-OF-CODE>\".\n\n{args.target_lang}:\n"
                outputs = model.codegen(prompt,
                    do_sample=not args.greedy,
                    num_samples=args.n_samples - sidx,
                    max_length=args.max_length,
                )

                assert outputs, "No outputs from model!"
                for impl in outputs:
                    try:
                        with open(
                            os.path.join(workdir, p_name, f"{sidx}{EXTENSIONS[args.target_lang]}"),
                            "w",
                            encoding="utf-8",
                        ) as f:
                            if model.conversational:
                                f.write(impl)
                            else:
                                f.write(prompt + impl)
                    except UnicodeEncodeError:
                        continue
                    sidx += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=str)
    parser.add_argument("--batch_size", default=1, type=int)
    parser.add_argument("--temperature", default=0.0, type=float)
    parser.add_argument("--dataset", required=True, type=str, choices=["codenet", "avatar"])
    parser.add_argument("--source_lang", required=True, type=str, choices=["C", "C++", "Java", "Python", "Go"])
    parser.add_argument("--target_lang", required=True, type=str, choices=["C", "C++", "Java", "Python", "Go"])
    parser.add_argument("--root", type=str, default="translations")
    parser.add_argument("--n_samples", default=1, type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--greedy", action="store_true")
    parser.add_argument("--ngpus", default=1, type=int)
    parser.add_argument("--max_length", default=1024, type=int)
    args = parser.parse_args()

    if args.greedy and (args.temperature != 0 or args.batch_size != 1 or args.n_samples != 1):
        args.temperature = 0
        args.batch_size = 1
        args.n_samples = 1
        print("Greedy decoding ON (--greedy): setting batch_size=1, n_samples=1, temperature=0")

    # Make project dir
    os.makedirs(args.root, exist_ok=True)
    # Make dataset dir
    os.makedirs(os.path.join(args.root, args.dataset), exist_ok=True)
    # Make dir for codes generated by each model
    args.model = args.model.lower()
    model = make_model(
        name=args.model, batch_size=args.batch_size, temperature=args.temperature, ngpus=args.ngpus
    )
    workdir = os.path.join(
        args.root,
        args.dataset,
        args.model,
        args.source_lang,
        args.target_lang,
        f"temperature_{args.temperature}"
    )
    os.makedirs(workdir, exist_ok=True)
    
    with open(os.path.join(workdir, "model.txt"), "w") as f:
        f.write(str(model.__dict__))
    
    logging.basicConfig(filename=os.path.join(workdir, 'log.log'), level=logging.INFO, format='%(asctime)s %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logging.info(f"translation started with args: {args}")

    translate(args, workdir=workdir, model=model)

    logging.info(f"translation finished")


if __name__ == "__main__":
    main()
