{
  description = "homeradio";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
  }: let
    lib = nixpkgs.lib;
    # pactl and mpv routing to PulseAudio sinks only make sense on Linux; the
    # dev shell is still useful for editing on a Mac.
    linuxSystems = ["x86_64-linux" "aarch64-linux"];
    allSystems = linuxSystems ++ ["x86_64-darwin" "aarch64-darwin"];
    forSystems = systems: f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
  in {
    formatter = forSystems allSystems (pkgs: pkgs.alejandra);

    packages = forSystems linuxSystems (pkgs: let
      python = pkgs.python3.withPackages (ps: [ps.flask]);
    in {
      default = pkgs.stdenvNoCC.mkDerivation {
        pname = "homeradio";
        version = "0.1.0";
        src = lib.fileset.toSource {
          root = ./.;
          fileset = lib.fileset.unions [
            ./homeradio
            ./static
            ./templates
            ./run.py
          ];
        };
        nativeBuildInputs = [pkgs.makeWrapper];
        installPhase = ''
          runHook preInstall
          mkdir -p $out/share/homeradio
          cp -r homeradio static templates run.py $out/share/homeradio/
          makeWrapper ${python.interpreter} $out/bin/homeradio \
            --add-flags $out/share/homeradio/run.py \
            --prefix PATH : ${lib.makeBinPath [pkgs.mpv pkgs.pulseaudio]}
          runHook postInstall
        '';
        meta = {
          description = "Web UI that plays internet radio streams on PulseAudio sinks";
          license = lib.licenses.agpl3Only;
          mainProgram = "homeradio";
          platforms = lib.platforms.linux;
        };
      };
    });

    devShells = forSystems allSystems (pkgs: let
      python = pkgs.python3;
    in {
      default = pkgs.mkShell {
        packages = [
          python
          pkgs.ruff
          python.pkgs.pip
          python.pkgs.virtualenv
          pkgs.mpv
        ];

        shellHook = ''
          if [ ! -d .venv ]; then
            ${python}/bin/python -m venv .venv
          fi
          source .venv/bin/activate
        '';
      };
    });

    nixosModules.default = {
      config,
      lib,
      pkgs,
      ...
    }: let
      cfg = config.services.homeradio;
    in {
      options.services.homeradio = {
        enable = lib.mkEnableOption "homeradio";
        package = lib.mkOption {
          type = lib.types.package;
          default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        };
        user = lib.mkOption {
          type = lib.types.str;
          description = ''
            User whose PipeWire/PulseAudio session plays the streams. The
            service runs in that user's systemd instance, which is kept
            running from boot so playback does not wait for a login.
          '';
        };
        host = lib.mkOption {
          type = lib.types.str;
          default = "0.0.0.0";
        };
        port = lib.mkOption {
          type = lib.types.port;
          default = 5000;
        };
        openFirewall = lib.mkOption {
          type = lib.types.bool;
          default = false;
        };
      };

      config = lib.mkIf cfg.enable {
        users.users.${cfg.user}.linger = true;

        systemd.user.services.homeradio = {
          description = "homeradio";
          wantedBy = ["default.target"];
          after = ["pipewire-pulse.service"];
          wants = ["pipewire-pulse.service"];
          # User units are installed for every user; only one instance may own
          # the port and the sinks.
          unitConfig.ConditionUser = cfg.user;
          environment = {
            HOMERADIO_HOST = cfg.host;
            HOMERADIO_PORT = toString cfg.port;
            HOMERADIO_DATA_DIR = "%S/homeradio";
          };
          serviceConfig = {
            ExecStart = lib.getExe cfg.package;
            StateDirectory = "homeradio";
            Restart = "always";
            RestartSec = 5;
          };
        };

        networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [cfg.port];
      };
    };
  };
}
