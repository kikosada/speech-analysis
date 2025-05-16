# Sales Pitch Analyzer

A powerful speech analysis application that provides detailed feedback on sales pitches using AI-powered speech recognition and analysis.

## Features

- Speech-to-text transcription with speaker identification
- Comprehensive pitch analysis including:
  - Duration and pacing
  - Argument structure
  - Use of persuasive language
  - Evidence and data usage
  - Response to objections
- Scoring system (1-10) for different aspects of the pitch
- Detailed feedback and improvement suggestions
- Support for both English and Spanish language pitches

## Prerequisites

- Python 3.8 or higher
- AssemblyAI API key
- OpenAI API key (for TTS features)

## Installation

1. Clone the repository:
```bash
git clone <your-repository-url>
cd <repository-name>
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
export ASSEMBLYAI_API_KEY='your_assemblyai_api_key'
export OPENAI_API_KEY='your_openai_api_key'  # Only needed for TTS features
```

## Usage

1. Basic transcription and analysis:
```bash
python transcribe.py --file path/to/your/audio.mp3
```

2. Generate TTS for sample pitches:
```bash
python hydrapro_tts.py
```

The application will generate several output files:
- `*_text.txt`: Raw transcription
- `*_analysis.txt`: Detailed analysis of the pitch
- `*_feedback.txt`: Specific feedback and suggestions
- `*_full.json`: Complete analysis data

## Output Files

The application generates several types of output files:

1. Transcription files (`*_text.txt`):
   - Contains the raw transcription of the audio
   - Includes speaker identification when available

2. Analysis files (`*_analysis.txt`):
   - Detailed breakdown of the pitch
   - Scores for different aspects
   - Key metrics and statistics

3. Feedback files (`*_feedback.txt`):
   - Specific suggestions for improvement
   - Actionable recommendations
   - Areas of strength and weakness

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [AssemblyAI](https://www.assemblyai.com/) for their excellent speech-to-text API
- [OpenAI](https://openai.com/) for TTS capabilities 