# A4 - Markov Text Generator

Dear APBC students,

Here is your next task.

In this assignment, you will write a small program that generates new
text from an input text using a Markov model. The program should read a
training text, find repeated contexts in it, and randomly choose one of
the continuations that actually occurs in the text.

The task is inspired by the idea that text can be generated without a
large language model: if we know the previous `k` characters or words,
we can choose the next character or word from examples observed in the
input text.

The assignment has two modes:

* character-based generation
* word-based generation

The order `k` of the Markov model should be configurable from the
command line.

Markov model
------------

A Markov model of order `k` uses the previous `k` units as context.
The units are characters in character mode and words in word mode.

For example, in a character-based model of order 3, the context could be

```
  the
```

and the program should look for all occurrences of `the` in the input
text. If the input contains continuations such as

```
  ther
  the 
  thes
```

then the next character should be chosen randomly among the observed
continuations.

In word mode, the same idea is applied to words. For example, with order
2, the context could be

```
  in the
```

and the program should choose the following word from all places where
`in the` occurs in the input text.

Task
----

Write a program that reads a text from a file and prints generated text
to standard output.

The program should be callable as

```
  $githubname-Markov.$suffix [options] [inputfile]
```

If an input file is given, the program reads the training text from this
file. If no input file is given, the program should read the training
text from standard input. The program should accept at most one input
file.

The program must support the following options:

```
  -o k       use Markov order k
  -w         use word-based generation instead of character-based generation
  -s seed    initialize the random number generator with seed
```

The default mode is character-based generation.

The option `-s` is important for testing and debugging: two runs with
the same input, the same options, and the same seed should produce the
same output.

Character-based mode
--------------------

In character-based mode, the model context consists of `k` consecutive
characters.

Your program should:

* read the full input text;
* use the order `k` supplied with `-o`;
* start the generated text with the first `k` characters of the input;
* repeatedly find all positions in the input where the current context
  occurs;
* choose one of these positions randomly;
* print the character that follows this occurrence;
* update the current context by shifting it one character to the right;
* stop when no valid continuation is possible.

The output should contain only the generated text. Error messages or
warnings should be printed to standard error.

Word-based mode
---------------

If the option `-w` is given, the model context consists of `k`
consecutive words instead of `k` consecutive characters.

For this assignment, words may be defined simply as chunks of text
separated by whitespace. Punctuation does not have to be removed in word
mode. Thus, `word`, `word.`, and `word,` may be treated as different
words.

Your program should:

* read the full input text;
* use the order `k` supplied with `-o`;
* start the generated text with the first `k` words of the input;
* repeatedly find all occurrences of the current word context;
* choose one occurrence randomly;
* print the word that follows this occurrence;
* update the current context by shifting it one word to the right;
* stop when no valid continuation is possible.

For readability, the generated word-based output may be wrapped after
approximately 70 characters per line.

Input handling
--------------

The input is ordinary text. Empty lines and line breaks may be treated as
whitespace.

For example, the following input

```
  one fish two fish
  red fish blue fish
```

may be internally treated as

```
  one fish two fish red fish blue fish
```

Your program does not need to handle extremely large files, but it
should work for normal text files used in the tests.

Because the program uses randomness, different seeds may produce
different generated texts. However, using the same seed should make the
output reproducible.


Hints
-----

* A simple solution can store a dictionary from contexts to possible
  continuations. For example, the key can be a string of `k` characters
  or a tuple/list of `k` words, and the value can be a list of observed
  next characters or words.

* A more memory-efficient solution can store suffixes of the input text,
  sort them, and use binary search to find all suffixes beginning with
  the current context.

* In word mode, it is useful to store only positions that start at the
  beginning of a word.

* Make sure that the program does not print debugging information to
  standard output. Standard output should contain only the generated
  text.

* Test small inputs first. For example, short repetitive texts such as
  `one fish two fish red fish blue fish` are useful for checking whether
  your contexts and continuations are correct.

* Higher Markov orders usually copy longer fragments from the input,
  while lower Markov orders usually produce more random-looking text.

Happy hacking!