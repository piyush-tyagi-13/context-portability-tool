class Ctxkit < Formula
  include Language::Python::Virtualenv

  desc "Context portability and knowledge ingestion tool — bridge your markdown vault to any subscription LLM"
  homepage "https://github.com/piyush-tyagi-13/context-portability-tool"
  url "https://files.pythonhosted.org/packages/a3/39/2009dec8daf3b19a9deb66424274e7b4e081bd35b1a687558cf3b9c4278d/ctxkit_ai-1.2.0.tar.gz"
  sha256 "51a3863a34c585765ceb7b55a07a431f8123798d8ca5139b347b3edec72240d8"
  license "MIT"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3.12")
    venv.pip_install "ctxkit-ai==#{version}"
    bin.install_symlink libexec/"bin/ctxkit"
  end

  test do
    assert_match "ctxkit", shell_output("#{bin}/ctxkit --help")
  end
end
