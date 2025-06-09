class BaseTranscriber:
    def transcribe(self, audio_path):
        raise NotImplementedError("Debes implementar el método transcribe en la subclase.") 