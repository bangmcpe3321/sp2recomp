using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Runtime.Serialization;
using Forms = System.Windows.Forms;
namespace Sp2Recomp.Launcher {
    [DataContract] public sealed class InputMapping {
        [DataMember] public string Action;
        [DataMember] public string Keys;
    }
    public sealed class InputDefinition {
        public readonly string Action, Label, Defaults, Group;
        public InputDefinition(string action,string label,string defaults,string group) { Action=action;Label=label;Defaults=defaults;Group=group; }
    }
    public static class InputOptions {
        public static readonly InputDefinition[] All = {
            new InputDefinition("LEFT","Move left","65,37","Movement"), new InputDefinition("RIGHT","Move right","68,39","Movement"),
            new InputDefinition("UP","Move forward / up","87,38","Movement"), new InputDefinition("DOWN","Move backward / down","83,40","Movement"),
            new InputDefinition("A","Confirm / interact · A","70","Actions"), new InputDefinition("B","Jump / back · B","32","Actions"),
            new InputDefinition("X","Game menu · X","74","Actions"), new InputDefinition("Y","Reset camera · Y","75","Actions"),
            new InputDefinition("L","L button","81","Actions"), new InputDefinition("R","Sub weapon · R","69","Actions"),
            new InputDefinition("ZL","Squid / swim · ZL","16,90","Actions"), new InputDefinition("ZR","Shoot · ZR","1,67","Actions"),
            new InputDefinition("PLUS","Plus (+)","13","Actions"), new InputDefinition("MINUS","Minus (−)","27","Actions"),
            new InputDefinition("STICK_L","Left stick click","0","Additional buttons"), new InputDefinition("STICK_R","Special / right stick click","0","Additional buttons"),
            new InputDefinition("DPAD_LEFT","D-pad left","0","Additional buttons"), new InputDefinition("DPAD_UP","D-pad up","0","Additional buttons"),
            new InputDefinition("DPAD_RIGHT","D-pad right","0","Additional buttons"), new InputDefinition("DPAD_DOWN","D-pad down","0","Additional buttons")
        };
        public static bool Valid(string value) {
            if(value=="0")return true;
            if(string.IsNullOrEmpty(value))return false;
            var parts=value.Split(','); if(parts.Length>4)return false;
            var seen=new HashSet<int>();
            foreach(var part in parts) {
                int code;
                if(part.Length==0 || part.Length>3 || part.Any(c=>c<'0'||c>'9') || !int.TryParse(part,NumberStyles.None,CultureInfo.InvariantCulture,out code) || code<1 || code>254 || !seen.Add(code))return false;
            }
            return true;
        }
        public static void Ensure(Settings s) {
            var old=s.InputMappings;
            s.InputMappings=All.Select(d=> {
                var item=old==null?null:old.LastOrDefault(m=>m!=null&&m.Action==d.Action&&Valid(m.Keys));
                return new InputMapping {Action=d.Action,Keys=item==null?d.Defaults:item.Keys};
            }).ToList();
        }
        public static string Codes(Settings s,string action) {
            var definition=All.First(d=>d.Action==action);
            var item=s.InputMappings==null?null:s.InputMappings.LastOrDefault(m=>m!=null&&m.Action==action&&Valid(m.Keys));
            return item==null?definition.Defaults:item.Keys;
        }
        public static void Assign(Settings s,string action,string keys) {
            if(!Valid(keys))throw new ArgumentException("Invalid key binding.");
            Ensure(s);s.InputMappings.First(m=>m.Action==action).Keys=keys;
        }
        public static string KeyName(int code) {
            switch(code) {
                case 0:return "Unassigned";case 1:return "Left mouse";case 2:return "Right mouse";case 4:return "Middle mouse";
                case 5:return "Mouse 4";case 6:return "Mouse 5";case 16:return "Shift";case 17:return "Ctrl";case 18:return "Alt";
                case 13:return "Enter";case 27:return "Esc";case 32:return "Space";
                default:return ((Forms.Keys)code).ToString();
            }
        }
        public static string Display(string keys) { return string.Join(" / ",keys.Split(',').Select(v=>KeyName(int.Parse(v,CultureInfo.InvariantCulture))).ToArray()); }
        public static int Normalize(int code) { if(code==160||code==161)return 16;if(code==162||code==163)return 17;if(code==164||code==165)return 18;return code; }
        public static bool Reserved(int code) { return code==112||code==114||code==122; } // F1 mouse lock, F3 overlay, F11 fullscreen
    }
}
